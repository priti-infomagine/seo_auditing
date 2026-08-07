"""
Service layer for refresh token rotation.

Steps:
    1. Decode the old refresh token (validate JWT)
    2. Hash the old token and look it up in DB
    3. Check if token is revoked or expired
    4. Revoke the old token (rotation)
    5. Blacklist the old access token (by JTI)
    6. Generate new access + refresh tokens
    7. Store new refresh token hash in DB
    8. Return new token pair
"""
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.modules.auth.models.refresh_token import RefreshToken
from app.modules.auth.models.token_blacklist import TokenBlacklist
from app.modules.auth.schemas.refresh import (
    RefreshTokenRequest,
    RefreshTokenResponse,
)
from app.modules.auth.utils.auth_utils import create_access_token, create_refresh_token, decode_token
from app.core.security import hash_token


@dataclass
class RefreshResult:
    """Internal result containing both tokens (refresh goes to cookie)."""

    response: RefreshTokenResponse
    refresh_token: str


class RefreshTokenService:
    """Encapsulates refresh token rotation logic."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def execute(
        self,
        request: RefreshTokenRequest,
        old_access_token_jti: str | None = None,
        old_access_token_expires_at: datetime | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> RefreshResult:
        # ── 1. Decode the old refresh token ────────────────────────────
        try:
            payload = decode_token(request.refresh_token)
        except JWTError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired refresh token.",
            )

        # Ensure it's a refresh token
        if payload.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type.",
            )

        subject = payload["sub"]

        # ── 2. Hash the old token and look it up in DB ─────────────────
        token_hash = hash_token(request.refresh_token)
        result = await self.db.execute(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )
        stored_token = result.scalar_one_or_none()

        if stored_token is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token not found.",
            )

        # ── 3. Check if token is revoked or expired ────────────────────
        if stored_token.is_revoked:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token has been revoked.",
            )

        if datetime.now(timezone.utc) > stored_token.expires_at:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token has expired.",
            )

        # ── 4. Update last_used_at on the old token ────────────────────
        stored_token.last_used_at = datetime.now(timezone.utc)

        # ── 5. Revoke the old token (rotation) ─────────────────────────
        stored_token.is_revoked = True
        await self.db.flush()

        # ── 6. Blacklist the old access token (by JTI) ─────────────────
        if old_access_token_jti:
            blacklisted_entry = TokenBlacklist(
                id=uuid.uuid4(),
                jti=old_access_token_jti,
                user_id=stored_token.user_id,
                expires_at=old_access_token_expires_at,
                reason="token refresh",
            )
            self.db.add(blacklisted_entry)
            await self.db.flush()

        # ── 7. Generate new tokens ─────────────────────────────────────
        new_access_token = create_access_token(subject)
        new_refresh_token = create_refresh_token(subject)

        # ── 8. Store new refresh token hash in DB (with device info) ───
        new_token_hash = hash_token(new_refresh_token)
        rt_expires_at = datetime.now(timezone.utc) + timedelta(
            days=settings.REFRESH_TOKEN_EXPIRE_DAYS
        )

        new_rt_record = RefreshToken(
            id=uuid.uuid4(),
            user_id=stored_token.user_id,
            token_hash=new_token_hash,
            expires_at=rt_expires_at,
            is_revoked=False,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        self.db.add(new_rt_record)
        await self.db.commit()

        # ── 9. Return new token pair ───────────────────────────────────
        return RefreshResult(
            response=RefreshTokenResponse(access_token=new_access_token),
            refresh_token=new_refresh_token,
        )
