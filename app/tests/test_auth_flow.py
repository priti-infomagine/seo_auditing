"""
Integration test: register → verify OTP → logout (with token blacklist check).

Tests the full auth flow using the service layer directly with a real database.
Verifies that:
    1. A user can register and an OTP is stored
    2. OTP verification creates an access token with a JTI claim
    3. The access token is NOT blacklisted before logout
    4. Logout revokes the refresh token AND blacklists the access token
    5. The blacklisted access token is rejected by get_current_user
"""
import uuid
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import select

from app.core.jwt import decode_token
from app.core.security import get_current_user, hash_token
from app.modules.auth.models.otp import OTP, OTPType
from app.modules.auth.models.refresh_token import RefreshToken
from app.modules.auth.models.token_blacklist import TokenBlacklist
from app.modules.auth.models.users import User
from app.modules.auth.schemas.register import RegisterRequest
from app.modules.auth.schemas.verify_otp import VerifyOTPRequest
from app.modules.auth.schemas.logout import LogoutRequest
from app.modules.auth.services.register_service import RegisterService
from app.modules.auth.services.verify_otp_service import VerifyOTPService
from app.modules.auth.services.logout_service import LogoutService


async def test_register_verify_otp_logout_flow(db_session):
    """
    Test the complete auth flow:
    1. Register user → OTP stored
    2. Verify OTP → access + refresh tokens created
    3. Logout → refresh token revoked + access token blacklisted
    4. Blacklisted token is rejected by get_current_user
    """
    test_email = f"test_{uuid.uuid4().hex[:8]}@example.com"
    test_password = "Test@1234"
    test_name = "Test User"

    # ── Step 1: Register user ──────────────────────────────────────────
    register_service = RegisterService(db_session)
    register_req = RegisterRequest(
        name=test_name,
        email=test_email,
        password=test_password,
    )
    register_resp = await register_service.execute(register_req)
    assert register_resp.message == "OTP sent successfully"

    # ── Step 2: Fetch the OTP from the database ────────────────────────
    result = await db_session.execute(
        select(User).where(User.email == test_email)
    )
    user = result.scalar_one_or_none()
    assert user is not None, "User should exist after registration"
    assert user.is_verified is False, "User should NOT be verified yet"

    otp_result = await db_session.execute(
        select(OTP)
        .where(OTP.user_id == user.id)
        .order_by(OTP.created_at.desc())
        .limit(1)
    )
    otp_record = otp_result.scalar_one_or_none()
    assert otp_record is not None, "OTP should exist"
    assert otp_record.otp_type == OTPType.REGISTER_OTP
    assert otp_record.expires_at > datetime.now(timezone.utc), "OTP should not be expired"

    # ── Step 3: Verify OTP (auto-login) ────────────────────────────────
    verify_service = VerifyOTPService(db_session)
    verify_req = VerifyOTPRequest(email=test_email, otp=otp_record.otp)
    verify_result = await verify_service.execute(verify_req)

    assert verify_result.response.access_token is not None
    assert verify_result.refresh_token is not None

    # Verify user is now verified
    await db_session.refresh(user)
    assert user.is_verified is True, "User should be verified after OTP"

    # ── Step 4: Decode the access token and verify JTI ─────────────────
    access_payload = decode_token(verify_result.response.access_token)
    access_jti = access_payload.get("jti")
    assert access_jti is not None, "Access token should have a jti claim"
    assert access_payload.get("type") == "access"
    assert access_payload.get("sub") == str(user.id)

    # Convert exp timestamp to datetime
    exp_timestamp = access_payload.get("exp")
    access_token_expires_at = datetime.fromtimestamp(exp_timestamp, tz=timezone.utc)

    # Hash the refresh token for DB lookup
    rt_hash = hash_token(verify_result.refresh_token)

    # Verify the refresh token exists in DB and is NOT revoked
    rt_result = await db_session.execute(
        select(RefreshToken).where(RefreshToken.token_hash == rt_hash)
    )
    stored_rt = rt_result.scalar_one_or_none()
    assert stored_rt is not None, "Refresh token should be stored in DB"
    assert stored_rt.is_revoked is False, "Refresh token should NOT be revoked yet"
    assert stored_rt.user_id == user.id

    # ── Step 5: Verify the access token is NOT blacklisted yet ─────────
    bl_result = await db_session.execute(
        select(TokenBlacklist).where(TokenBlacklist.jti == access_jti)
    )
    assert bl_result.scalar_one_or_none() is None, (
        "Access token should NOT be blacklisted before logout"
    )

    # ── Step 6: Logout ─────────────────────────────────────────────────
    logout_service = LogoutService(db_session)
    logout_req = LogoutRequest(refresh_token=verify_result.refresh_token)
    logout_resp = await logout_service.execute(
        logout_req,
        access_token_jti=access_jti,
        access_token_expires_at=access_token_expires_at,
    )
    assert logout_resp.message == "Logged out successfully"

    # ── Step 7: Verify the refresh token is revoked ────────────────────
    await db_session.refresh(stored_rt)
    assert stored_rt.is_revoked is True, "Refresh token should be revoked after logout"

    # ── Step 8: Verify the access token IS blacklisted ─────────────────
    bl_result = await db_session.execute(
        select(TokenBlacklist).where(TokenBlacklist.jti == access_jti)
    )
    blacklisted = bl_result.scalar_one_or_none()
    assert blacklisted is not None, "Access token should be blacklisted after logout"
    assert blacklisted.jti == access_jti
    assert blacklisted.user_id == user.id
    assert blacklisted.reason == "logout"
    assert blacklisted.expires_at is not None

    # ── Step 9: Verify get_current_user rejects the blacklisted token ──
    mock_credentials = HTTPAuthorizationCredentials(
        scheme="Bearer",
        credentials=verify_result.response.access_token,
    )
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(credentials=mock_credentials, db=db_session)
    assert exc_info.value.status_code == 401
    assert "revoked" in exc_info.value.detail.lower()


async def test_logout_without_access_token(db_session):
    """
    Test that logout works even when no access token JTI is provided
    (e.g., the access token is already expired).
    The refresh token should still be revoked.
    """
    test_email = f"test_{uuid.uuid4().hex[:8]}@example.com"
    test_password = "Test@1234"

    register_service = RegisterService(db_session)
    await register_service.execute(
        RegisterRequest(name="Test User", email=test_email, password=test_password)
    )

    user = (await db_session.execute(
        select(User).where(User.email == test_email)
    )).scalar_one()

    otp_record = (await db_session.execute(
        select(OTP).where(OTP.user_id == user.id).order_by(OTP.created_at.desc()).limit(1)
    )).scalar_one()

    verify_service = VerifyOTPService(db_session)
    verify_result = await verify_service.execute(
        VerifyOTPRequest(email=test_email, otp=otp_record.otp)
    )

    # Logout WITHOUT providing access_token_jti (simulating expired token)
    logout_service = LogoutService(db_session)
    logout_req = LogoutRequest(refresh_token=verify_result.refresh_token)
    logout_resp = await logout_service.execute(logout_req)
    assert logout_resp.message == "Logged out successfully"

    # Verify the refresh token is still revoked
    rt_hash = hash_token(verify_result.refresh_token)
    stored_rt = (await db_session.execute(
        select(RefreshToken).where(RefreshToken.token_hash == rt_hash)
    )).scalar_one()
    assert stored_rt.is_revoked is True

    # Verify NO blacklist entry was created (since no JTI was provided)
    access_jti = decode_token(verify_result.response.access_token).get("jti")
    if access_jti:
        blacklisted = (await db_session.execute(
            select(TokenBlacklist).where(TokenBlacklist.jti == access_jti)
        )).scalar_one_or_none()
        assert blacklisted is None, (
            "No blacklist entry should exist when JTI was not provided"
        )


async def test_logout_revoked_token_raises_error(db_session):
    """
    Test that calling logout twice with the same refresh token raises an error.
    The second call should fail because the token is already revoked.
    """
    test_email = f"test_{uuid.uuid4().hex[:8]}@example.com"
    test_password = "Test@1234"

    register_service = RegisterService(db_session)
    await register_service.execute(
        RegisterRequest(name="Test User", email=test_email, password=test_password)
    )
    user = (await db_session.execute(
        select(User).where(User.email == test_email)
    )).scalar_one()
    otp_record = (await db_session.execute(
        select(OTP).where(OTP.user_id == user.id).order_by(OTP.created_at.desc()).limit(1)
    )).scalar_one()

    verify_service = VerifyOTPService(db_session)
    verify_result = await verify_service.execute(
        VerifyOTPRequest(email=test_email, otp=otp_record.otp)
    )

    # First logout - should succeed
    logout_service = LogoutService(db_session)
    access_jti = decode_token(verify_result.response.access_token).get("jti")
    exp_ts = decode_token(verify_result.response.access_token).get("exp")
    exp_dt = datetime.fromtimestamp(exp_ts, tz=timezone.utc)

    resp1 = await logout_service.execute(
        LogoutRequest(refresh_token=verify_result.refresh_token),
        access_token_jti=access_jti,
        access_token_expires_at=exp_dt,
    )
    assert resp1.message == "Logged out successfully"

    # Second logout with the same refresh token - should raise 401
    with pytest.raises(HTTPException) as exc_info:
        await logout_service.execute(
            LogoutRequest(refresh_token=verify_result.refresh_token),
        )
    assert exc_info.value.status_code == 401
    assert "already revoked" in exc_info.value.detail.lower()