"""
Service layer for password reset flow.

Endpoints:
    1. POST /auth/forgot-password  → Generate & send OTP (type: forgot_pass_otp)
    2. POST /auth/verify-reset-otp → Verify OTP, change type to reset_pass_otp
    3. POST /auth/reset-password   → Reset password (requires reset_pass_otp)
"""
import random
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.modules.auth.models.otp import OTP, OTPType
from app.modules.auth.models.users import User
from app.modules.auth.schemas.forgot_password import (
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    ResetPasswordRequest,
    ResetPasswordResponse,
    VerifyResetOTPRequest,
    VerifyResetOTPResponse,
)
from app.core.security import hash_password, verify_password
from app.modules.auth.utils.email_utils import  send_password_reset_otp_email
from app.modules.auth.utils.auth_utils import generate_otp_code 

class ForgotPasswordService:
    """Generate and send a forgot-password OTP."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def execute(self, request: ForgotPasswordRequest) -> ForgotPasswordResponse:
        try:
            # ── 1. Find user by email ──────────────────────────────────────
            result = await self.db.execute(
                select(User).where(User.email == request.email)
            )
            user = result.scalar_one_or_none()
            if user is None:
                # Don't reveal whether the email exists (security best practice)
                return ForgotPasswordResponse(message="OTP sent successfully")

            # ── 2. Invalidate any existing forgot-password OTPs for this user ──
            existing_otps = await self.db.execute(
                select(OTP).where(
                    OTP.user_id == user.id,
                    OTP.otp_type == OTPType.FORGOT_PASS_OTP,
                )
            )
            for otp_record in existing_otps.scalars().all():
                await self.db.delete(otp_record)
            await self.db.flush()

            
            otp_code, expires_at = generate_otp_code()

            otp = OTP(
                id=uuid.uuid4(),
                user_id=user.id,
                otp=otp_code,
                otp_type=OTPType.FORGOT_PASS_OTP,
                expires_at=expires_at,
            )
            self.db.add(otp)
            await self.db.flush()

            # ── NOTE: In production, send OTP via email/SMS here through background tasks───────────
            
            await send_password_reset_otp_email(user.email, otp_code)
            print(f"[FORGOT PASSWORD] OTP for {user.email}: {otp_code}")

            return ForgotPasswordResponse(message="OTP sent successfully")

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"An unexpected error occurred: {str(e)}",
            )


class VerifyResetOTPService:
    """Verify the forgot-password OTP and change its type to reset_pass_otp."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def execute(self, request: VerifyResetOTPRequest) -> VerifyResetOTPResponse:
        try:
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

            # ── 2. Find latest valid FORGOT_PASS_OTP for this user ─────────
            otp_result = await self.db.execute(
                select(OTP)
                .where(
                    OTP.user_id == user.id,
                    OTP.otp_type == OTPType.FORGOT_PASS_OTP,
                )
                .order_by(OTP.created_at.desc())
                .limit(1)
            )
            otp_record = otp_result.scalar_one_or_none()
            if otp_record is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No OTP found. Please request a new OTP.",
                )

            # ── 3. Check OTP expiry ────────────────────────────────────────
            if datetime.now(timezone.utc) > otp_record.expires_at:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="OTP has expired. Please request a new OTP.",
                )

            # ── 4. Verify OTP value ────────────────────────────────────────
            if otp_record.otp != request.otp:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid OTP.",
                )

            # ── 5. Change OTP type to RESET_PASS_OTP ───────────────────────
            otp_record.otp_type = OTPType.RESET_PASS_OTP
            await self.db.flush()

            return VerifyResetOTPResponse(message="OTP verified successfully")

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"An unexpected error occurred: {str(e)}",
            )


class ResetPasswordService:
    """Reset the user's password after OTP verification."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def execute(self, request: ResetPasswordRequest) -> ResetPasswordResponse:
        try:
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

            # ── 2. Find latest valid RESET_PASS_OTP for this user ──────────
            otp_result = await self.db.execute(
                select(OTP)
                .where(
                    OTP.user_id == user.id,
                    OTP.otp_type == OTPType.RESET_PASS_OTP,
                )
                .order_by(OTP.created_at.desc())
                .limit(1)
            )
            otp_record = otp_result.scalar_one_or_none()
            if otp_record is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="OTP not verified. Please verify OTP first.",
                )

            # ── 3. Check OTP expiry ────────────────────────────────────────
            if datetime.now(timezone.utc) > otp_record.expires_at:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="OTP has expired. Please request a new OTP.",
                )

            # ── 4. Check new password is not same as current password ──────
            if verify_password(request.new_password, user.password_hash):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="New password cannot be the same as the current password.",
                )

            # ── 5. Hash new password and update user ───────────────────────
            hashed_pw = hash_password(request.new_password)
            user.password_hash = hashed_pw
            await self.db.flush()

            # ── 6. Delete the used OTP record ──────────────────────────────
            await self.db.delete(otp_record)
            await self.db.flush()

            return ResetPasswordResponse(message="Password reset successfully")

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"An unexpected error occurred: {str(e)}",
            )