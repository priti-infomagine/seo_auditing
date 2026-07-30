"""
Service layer for user logout.

Steps:
    1. Hash the provided refresh token
    2. Look it up in the DB
    3. Revoke the token
    4. Return success
"""
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth_models.refresh_token import RefreshToken
from app.schemas.auth_schemas.logout import LogoutRequest, LogoutResponse
from app.core.security import hash_token


class LogoutService:
    """Encapsulates logout business logic."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def execute(self, request: LogoutRequest) -> LogoutResponse:
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

        # ── 3. Revoke the token ────────────────────────────────────────
        stored_token.is_revoked = True
        await self.db.flush()

        # ── 4. Return success ──────────────────────────────────────────
        return LogoutResponse(message="Logged out successfully")