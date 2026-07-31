"""
Password reset endpoints.

Endpoints:
    POST /auth/password-reset/forgot-password  → Request OTP
    POST /auth/password-reset/verify-reset-otp → Verify OTP
    POST /auth/password-reset/reset-password   → Reset password
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.logger import logger
from app.schemas.auth_schemas.forgot_password import (
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    ResetPasswordRequest,
    ResetPasswordResponse,
    VerifyResetOTPRequest,
    VerifyResetOTPResponse,
)
from app.services.auth_services.password_reset_service import (
    ForgotPasswordService,
    ResetPasswordService,
    VerifyResetOTPService,
)

router = APIRouter()


@router.post(
    "/request_otp",
    response_model=ForgotPasswordResponse,
    status_code=200,
    summary="Request password_reset OTP",
)
async def forgot_password(
    body: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db),
) -> ForgotPasswordResponse:
    """Send a password reset OTP to the user's email."""
    logger.info("POST /auth/forgot-pass/request_otp - Forgot password endpoint called")
    service = ForgotPasswordService(db)
    return await service.execute(body)


@router.post(
    "/verify-reset-otp",
    response_model=VerifyResetOTPResponse,
    status_code=200,
    summary="Verify password_reset OTP",
)
async def verify_reset_otp(
    body: VerifyResetOTPRequest,
    db: AsyncSession = Depends(get_db),
) -> VerifyResetOTPResponse:
    """Verify the OTP and authorize password reset."""
    logger.info("POST /auth/forgot-pass/verify-reset-otp - Verify reset OTP endpoint called")
    service = VerifyResetOTPService(db)
    return await service.execute(body)


@router.post(
    "/confirm-password",
    response_model=ResetPasswordResponse,
    status_code=200,
    summary="Reset password after OTP verification",
)
async def reset_password(
    body: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
) -> ResetPasswordResponse:
    """Reset the user's password after successful OTP verification."""
    logger.info("POST /auth/forgot-pass/confirm-password - Reset password endpoint called")
    service = ResetPasswordService(db)
    return await service.execute(body)
