"""
Service layer for refresh token rotation.

Steps:
    1. Decode the old refresh token (validate JWT)
    2. Hash the old token and look it up in DB
    3. Check if token is revoked or expired
    4. Revoke the old token (rotation)
    5. Generate new access + refresh tokens
    6. Store new refresh token hash in DB
    7. Return new token pair
"""
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.auth_models.refresh_token import RefreshToken
from app.schemas.auth_schemas.refresh import (
    RefreshTokenRequest,
    RefreshTokenResponse,
)
from app.core.jwt import create_access_token, create_refresh_token, decode_token
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

    async def execute(self, request: RefreshTokenRequest) -> RefreshResult:
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

        # ── 4. Revoke the old token (rotation) ─────────────────────────
        stored_token.is_revoked = True
        await self.db.flush()

        # ── 5. Generate new tokens ─────────────────────────────────────
        new_access_token = create_access_token(subject)
        new_refresh_token = create_refresh_token(subject)

        # ── 6. Store new refresh token hash in DB ──────────────────────
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
        )
        self.db.add(new_rt_record)
        await self.db.flush()

        # ── 7. Return new token pair ───────────────────────────────────
        return RefreshResult(
            response=RefreshTokenResponse(access_token=new_access_token),
            refresh_token=new_refresh_token,
        )