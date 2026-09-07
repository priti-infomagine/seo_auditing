"""
Service layer for user login.

Steps:
    1. Find user by email
    2. Check if user is verified
    3. Verify password
    4. Generate JWT tokens
    5. Store refresh token hash in DB (with device info)
    6. Return tokens
"""
import uuid
from datetime import datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.datetime_utils import utc_now
from app.modules.auth.models.refresh_token import RefreshToken
from app.modules.auth.models.users import User
from app.modules.auth.schemas.login import LoginRequest, LoginResponse
from app.modules.auth.utils.auth_utils import create_access_token, create_refresh_token
from app.core.security import hash_token, verify_password


class LoginService:
    """Encapsulates login business logic."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def execute(
        self,
        request: LoginRequest,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> LoginResponse:
        # ── 1. Find user by email ──────────────────────────────────────
        result = await self.db.execute(
            select(User).where(User.email == request.email)
        )
        user = result.scalar_one_or_none()
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password.",
            )

        # ── 2. Check if user is verified ───────────────────────────────
        if not user.is_verified:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Email not verified. Please verify your OTP first.",
            )

        # ── 3. Verify password ─────────────────────────────────────────
        if not verify_password(request.password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password.",
            )

        # ── 4. Generate JWT tokens ─────────────────────────────────────
        subject = str(user.id)
        access_token = create_access_token(subject)
        refresh_token = create_refresh_token(subject)

        # ── 5. Store refresh token hash in DB (with device info) ───────
        token_hash = hash_token(refresh_token)
        rt_expires_at = utc_now() + timedelta(
            days=settings.REFRESH_TOKEN_EXPIRE_DAYS
        )

        rt_record = RefreshToken(
            id=uuid.uuid4(),
            user_id=user.id,
            token_hash=token_hash,
            expires_at=rt_expires_at,
            is_revoked=False,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        self.db.add(rt_record)
        await self.db.flush()

        # ── 6. Return tokens ───────────────────────────────────────────
        return LoginResponse(
            access_token=access_token,
            refresh_token=refresh_token,
        )
