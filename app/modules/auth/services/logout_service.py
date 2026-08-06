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
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
        access_token_jti: str | None = None,
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
        # -- check for if already revoked
        if stored_token.is_revoked:
            return LogoutResponse(
                message="Logged out successfully"
            )
        if stored_token.expires_at < datetime.now(timezone.utc):
            return LogoutResponse(
                message="Logged out successfully"
            )
        # ── 3. Revoke the token ────────────────────────────────────────
        stored_token.is_revoked = True
        

        # ── 4. Blacklist the access token (by JTI) ─────────────────────
        if access_token_jti:
            # Use the token's exp as the blacklist expiry; fallback to now if unavailable
            blacklist_expires_at = access_token_expires_at or datetime.now(timezone.utc)
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
