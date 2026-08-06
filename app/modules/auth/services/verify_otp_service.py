"""
Service layer for OTP verification.

Steps:
    1. Find user by email
    2. Find the latest valid OTP for that user
    3. Check OTP expiry
    4. Verify OTP value
    5. Mark user as verified
    6. Delete used OTP
    7. Generate JWT tokens (auto-login)
    8. Store refresh token hash in DB (with device info)
    9. Return tokens
"""
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.modules.auth.models.otp import OTP
from app.modules.auth.models.refresh_token import RefreshToken
from app.modules.auth.models.users import User
from app.modules.auth.schemas.verify_otp import (
    VerifyOTPRequest,
    VerifyOTPResponse,
)
from app.modules.auth.utils import create_access_token, create_refresh_token
from app.core.security import hash_token


@dataclass
class VerifyOTPResult:
    """Internal result — refresh token goes to cookie."""

    response: VerifyOTPResponse
    refresh_token: str


class VerifyOTPService:
    """Encapsulates OTP verification and auto-login logic."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def execute(
        self,
        request: VerifyOTPRequest,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> VerifyOTPResult:
        # ── 1. Find user by email ──────────────────────────────────────
        result = await self.db.execute(
            select(User).where(User.email == request.email)
        )
        user = result.scalar_one_or_none()
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found.",
            )

        # ── 2. Find latest valid OTP for this user ─────────────────────
        otp_result = await self.db.execute(
            select(OTP)
            .where(OTP.user_id == user.id)
            .order_by(OTP.created_at.desc())
            .limit(1)
        )
        otp_record = otp_result.scalar_one_or_none()
        if otp_record is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No OTP found. Please register again.",
            )

        # ── 3. Check OTP expiry ────────────────────────────────────────
        if datetime.now(timezone.utc) > otp_record.expires_at:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="OTP has expired. Please register again.",
            )
        if otp_record.attempts >= 5:
            raise HTTPException(
                status_code=400,
                detail="Too many attempts. Request a new OTP."
            )

        if otp_record.otp != request.otp:
            otp_record.attempts += 1
            await self.db.commit()

            raise HTTPException(
                status_code=400,
                detail="Invalid OTP."
            )

        # ── 4. Verify OTP value ────────────────────────────────────────
        if otp_record.otp != request.otp:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid OTP.",
            )

        # ── 5. Mark user as verified ───────────────────────────────────
        user.is_verified = True
        await self.db.flush()

        # ── 6. Delete used OTP ─────────────────────────────────────────
        await self.db.delete(otp_record)
        await self.db.flush()

        # ── 7. Generate JWT tokens (auto-login) ────────────────────────
        subject = str(user.id)
        access_token = create_access_token(subject)
        refresh_token = create_refresh_token(subject)

        # ── 8. Store refresh token hash in DB (with device info) ───────
        token_hash = hash_token(refresh_token)
        rt_expires_at = datetime.now(timezone.utc) + timedelta(
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

        # ── 9. Return tokens ───────────────────────────────────────────\
        await self.db.commit()
        return VerifyOTPResult(
            response=VerifyOTPResponse(
                message="Email verified successfully",
                access_token=access_token,
            ),
            refresh_token=refresh_token,
        )
