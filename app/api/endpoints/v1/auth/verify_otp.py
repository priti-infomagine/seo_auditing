"""
POST /auth/verify-otp — Verify email OTP and auto-login.

Steps:
    1. Verify OTP
    2. Mark user as verified
    3. Store device info with refresh token
    4. Return JWT tokens (auto-login) — refresh token in HttpOnly cookie
"""
from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.logger import logger
from app.modules.auth.schemas.verify_otp import (
    VerifyOTPRequest,
    VerifyOTPResponse,
)
from app.modules.auth.services.verify_otp_service import VerifyOTPService

router = APIRouter()


@router.post(
    "",
    response_model=VerifyOTPResponse,
    status_code=200,
    summary="Verify email OTP and auto-login",
)
async def verify_otp(
    request: Request,
    body: VerifyOTPRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> VerifyOTPResponse:
    """Verify OTP, mark email as verified, and return JWT tokens."""
    logger.info("POST /auth/verify-otp - Verify OTP endpoint called")
    # Extract device info from request
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    service = VerifyOTPService(db)
    result = await service.execute(
        body,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    # Set refresh token as HttpOnly cookie
    response.set_cookie(
        key="refreshToken",
        value=result.refresh_token,
        httponly=True,
        secure=False,
        samesite="strict",
        path="/",
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,  # days → seconds
    )

    return result.response
