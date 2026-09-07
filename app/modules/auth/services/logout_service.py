"""
Service layer for user logout.

Steps:
    1. Hash the provided refresh token
    2. Look it up in the DB
    3. Revoke the token
    4. Blacklist the access token (by JTI)
    5. Return success
"""
import uuid
from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import utc_now
from app.modules.auth.models.refresh_token import RefreshToken
from app.modules.auth.models.token_blacklist import TokenBlacklist
from app.modules.auth.schemas.logout import LogoutRequest, LogoutResponse
from app.core.security import hash_token


class LogoutService:
    """Encapsulates logout business logic."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def execute(
        self,
        request: LogoutRequest,
        access_token_jti: str,
        access_token_expires_at: datetime | None = None,
    ) -> LogoutResponse:
        # ── 1. Hash the provided refresh token ─────────────────────────
        token_hash = hash_token(request.refresh_token)

        # ── 2. Look it up in the DB ────────────────────────────────────
        result = await self.db.execute(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )
        stored_token = result.scalar_one_or_none()
        
        if stored_token is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Refresh token not found.",
            )
        
        # ── 3. Revoke refresh token if it hasn't expired yet ───────────
        if stored_token.expires_at >= utc_now():
            stored_token.is_revoked = True

        # ── 4. Blacklist the access token (by JTI) ─────────────────────
        existing_blacklist = await self.db.execute(
            select(TokenBlacklist).where(TokenBlacklist.jti == access_token_jti)
        )
        if existing_blacklist.scalar_one_or_none() is None:
            blacklist_expires_at = access_token_expires_at or utc_now()
            blacklisted_entry = TokenBlacklist(
                jti=access_token_jti,
                user_id=stored_token.user_id,
                expires_at=blacklist_expires_at,
                reason="logout",
            )
            self.db.add(blacklisted_entry)
        await self.db.commit()
        
        # ── 5. Return success ──────────────────────────────────────────
        return LogoutResponse(message="Logged out successfully")
