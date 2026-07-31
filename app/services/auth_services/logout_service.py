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

from app.models.auth_models.refresh_token import RefreshToken
from app.models.auth_models.token_blacklist import TokenBlacklist
from app.schemas.auth_schemas.logout import LogoutRequest, LogoutResponse
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
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Token already revoked.",
            )
        # ── 3. Revoke the token ────────────────────────────────────────
        stored_token.is_revoked = True
        

        # ── 4. Blacklist the access token (by JTI) ─────────────────────
        print(f"[DEBUG LOGOUT SERVICE] access_token_jti provided: {access_token_jti}")
        print(f"[DEBUG LOGOUT SERVICE] access_token_expires_at provided: {access_token_expires_at}")
        
        if access_token_jti:
            # Use the token's exp as the blacklist expiry; fallback to now if unavailable
            blacklist_expires_at = access_token_expires_at or datetime.now(timezone.utc)
            print(f"[DEBUG LOGOUT SERVICE] Creating TokenBlacklist entry with jti={access_token_jti}, expires_at={blacklist_expires_at}")
            blacklisted_entry = TokenBlacklist(
                jti=access_token_jti,
                user_id=stored_token.user_id,
                expires_at=blacklist_expires_at,
                reason="logout",
            )
            self.db.add(blacklisted_entry)
            print(f"[DEBUG LOGOUT SERVICE] TokenBlacklist entry added to session")
        else:
            print(f"[DEBUG LOGOUT SERVICE] SKIPPING blacklist - access_token_jti is falsy")
        
        print(f"[DEBUG LOGOUT SERVICE] Committing transaction...")
        await self.db.commit()
        print(f"[DEBUG LOGOUT SERVICE] Transaction committed successfully")
        
        # ── 5. Return success ──────────────────────────────────────────
        return LogoutResponse(message="Logged out successfully")
