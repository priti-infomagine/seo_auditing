"""
Focused unit test for logout token blacklisting.

Creates a user and a refresh token directly in the DB, then invokes
LogoutService and asserts that the access token JTI is stored in
token_blacklist and the refresh token is revoked. Does not create or drop tables.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.core.security import hash_token
from app.modules.auth.models.refresh_token import RefreshToken
from app.modules.auth.models.token_blacklist import TokenBlacklist
from app.modules.auth.models.users import User
from app.modules.auth.schemas.logout import LogoutRequest
from app.modules.auth.services.logout_service import LogoutService


@pytest.mark.asyncio
async def test_logout_blacklists_access_token_and_revokes_refresh_token(db_session):
    test_email = f"logout_test_{uuid.uuid4().hex[:8]}@example.com"
    test_password_hash = "hashed_test_password"
    test_name = "Logout Test User"
    access_token_jti = str(uuid.uuid4())

    user = User(
        name=test_name,
        email=test_email,
        password_hash=test_password_hash,
        is_verified=True,
    )
    db_session.add(user)
    await db_session.flush()

    raw_refresh_token = f"refresh_{uuid.uuid4().hex}"
    rt_hash = hash_token(raw_refresh_token)
    refresh_token = RefreshToken(
        user_id=user.id,
        token_hash=rt_hash,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        is_revoked=False,
    )
    db_session.add(refresh_token)
    await db_session.flush()

    assert refresh_token.id is not None

    logout_service = LogoutService(db_session)
    logout_req = LogoutRequest(refresh_token=raw_refresh_token, access_token="dummy")
    logout_resp = await logout_service.execute(
        logout_req,
        access_token_jti=access_token_jti,
        access_token_expires_at=datetime.now(timezone.utc) + timedelta(
            minutes=30
        ),
    )
    assert logout_resp.message == "Logged out successfully"

    await db_session.refresh(refresh_token)
    assert refresh_token.is_revoked is True

    blacklisted = await db_session.execute(
        select(TokenBlacklist).where(TokenBlacklist.jti == access_token_jti)
    )
    entry = blacklisted.scalar_one_or_none()
    assert entry is not None
    assert entry.user_id == user.id
    assert entry.reason == "logout"