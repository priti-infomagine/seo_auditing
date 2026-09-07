"""
API-level tests for POST /auth/logout.

Covers:
- logout with access token in Authorization header
- logout with access token in JSON body
- logout without access token returns 400
- logout with invalid access token returns 401
- blacklisted access token is rejected by get_current_user
- double logout does not create duplicate blacklist entries
"""
import uuid

import pytest
import httpx
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import select

from app.core.security import get_current_user, hash_token
from app.main import app
from app.modules.auth.models.otp import OTP, OTPType
from app.modules.auth.models.refresh_token import RefreshToken
from app.modules.auth.models.token_blacklist import TokenBlacklist
from app.modules.auth.models.users import User
from app.modules.auth.schemas.register import RegisterRequest
from app.modules.auth.schemas.verify_otp import VerifyOTPRequest
from app.modules.auth.services.register_service import RegisterService
from app.modules.auth.services.verify_otp_service import VerifyOTPService


@pytest.mark.asyncio
async def test_logout_with_access_token_in_header(db_session):
    """
    Test the full API flow:
    1. Register user
    2. Verify OTP
    3. Login to get fresh access + refresh tokens
    4. Call POST /auth/logout with access token in Authorization header
    5. Verify refresh token is revoked
    6. Verify access token is blacklisted
    7. Verify get_current_user rejects the blacklisted token
    """
    test_email = f"test_{uuid.uuid4().hex[:8]}@example.com"
    test_password = "Test@1234"

    # Register
    register_service = RegisterService(db_session)
    register_resp = await register_service.execute(
        RegisterRequest(name="Test User", email=test_email, password=test_password)
    )
    assert register_resp.message == "OTP sent successfully"

    user = (await db_session.execute(
        select(User).where(User.email == test_email)
    )).scalar_one()

    otp_record = (await db_session.execute(
        select(OTP).where(OTP.user_id == user.id).order_by(OTP.created_at.desc()).limit(1)
    )).scalar_one()

    # Verify OTP
    verify_service = VerifyOTPService(db_session)
    verify_result = await verify_service.execute(
        VerifyOTPRequest(email=test_email, otp=otp_record.otp)
    )
    assert verify_result.response.access_token is not None
    assert verify_result.refresh_token is not None

    access_token = verify_result.response.access_token
    refresh_token = verify_result.refresh_token

    # Decode JTI before logout
    from app.modules.auth.utils.auth_utils import decode_token
    access_payload = decode_token(access_token)
    access_jti = access_payload.get("jti")
    assert access_jti is not None

    # Logout via API with access token in header
    async with httpx.AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/auth/logout",
            headers={"Authorization": f"Bearer {access_token}"},
            cookies={"refresh_token": refresh_token},
        )
    assert response.status_code == 200
    assert response.json()["message"] == "Logged out successfully"

    # Verify refresh token is revoked
    rt_hash = hash_token(refresh_token)
    stored_rt = (await db_session.execute(
        select(RefreshToken).where(RefreshToken.token_hash == rt_hash)
    )).scalar_one()
    assert stored_rt.is_revoked is True

    # Verify access token is blacklisted
    blacklisted = (await db_session.execute(
        select(TokenBlacklist).where(TokenBlacklist.jti == access_jti)
    )).scalar_one_or_none()
    assert blacklisted is not None
    assert blacklisted.jti == access_jti
    assert blacklisted.user_id == user.id
    assert blacklisted.reason == "logout"

    # Verify get_current_user rejects blacklisted token
    mock_credentials = HTTPAuthorizationCredentials(
        scheme="Bearer",
        credentials=access_token,
    )
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(credentials=mock_credentials, db=db_session)
    assert exc_info.value.status_code == 401
    assert "revoked" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_logout_with_access_token_in_body(db_session):
    """
    Test logout when access token is sent in the JSON body
    instead of the Authorization header.
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

    access_token = verify_result.response.access_token
    refresh_token = verify_result.refresh_token

    from app.modules.auth.utils.auth_utils import decode_token
    access_jti = decode_token(access_token).get("jti")
    assert access_jti is not None

    async with httpx.AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/auth/logout",
            json={"access_token": access_token},
            cookies={"refresh_token": refresh_token},
        )
    assert response.status_code == 200
    assert response.json()["message"] == "Logged out successfully"

    blacklisted = (await db_session.execute(
        select(TokenBlacklist).where(TokenBlacklist.jti == access_jti)
    )).scalar_one_or_none()
    assert blacklisted is not None


@pytest.mark.asyncio
async def test_logout_without_access_token_returns_400(db_session):
    """
    Test logout when no access token is provided.
    The endpoint must return 400 because access token is now required.
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

    async with httpx.AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/auth/logout",
            cookies={"refresh_token": verify_result.refresh_token},
        )
    assert response.status_code == 400
    assert "Access token is required" in response.json()["detail"]


@pytest.mark.asyncio
async def test_logout_with_invalid_access_token_returns_401(db_session):
    """
    Test logout when an invalid access token is provided.
    The endpoint must return 401.
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

    async with httpx.AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/auth/logout",
            json={"access_token": "invalid.token.here"},
            cookies={"refresh_token": verify_result.refresh_token},
        )
    assert response.status_code == 401
    assert "Invalid or expired access token" in response.json()["detail"]


@pytest.mark.asyncio
async def test_double_logout_returns_success(db_session):
    """
    Calling logout twice with the same refresh token should still succeed
    because the token was already revoked, but it should not create
    duplicate blacklist entries.
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

    access_token = verify_result.response.access_token
    refresh_token = verify_result.refresh_token

    from app.modules.auth.utils.auth_utils import decode_token
    access_jti = decode_token(access_token).get("jti")

    async with httpx.AsyncClient(app=app, base_url="http://test") as client:
        response1 = await client.post(
            "/api/v1/auth/logout",
            headers={"Authorization": f"Bearer {access_token}"},
            cookies={"refresh_token": refresh_token},
        )
        assert response1.status_code == 200

        response2 = await client.post(
            "/api/v1/auth/logout",
            headers={"Authorization": f"Bearer {access_token}"},
            cookies={"refresh_token": refresh_token},
        )
        assert response2.status_code == 200

    blacklisted_count = (await db_session.execute(
        select(TokenBlacklist).where(TokenBlacklist.jti == access_jti)
    )).scalars().all()
    assert len(blacklisted_count) == 1, "Should have exactly one blacklist entry"
