"""
POST /auth/refresh — Refresh access token using refresh token (rotation).

Revokes old refresh token, blacklists the old access token,
and issues a new pair.
Refresh token is read from an HttpOnly cookie, and the new one is set as a cookie.
Access token is read from the Authorization header.
"""
from datetime import timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.datetime_utils import utc_now
from app.modules.auth.utils.auth_utils import decode_token
from app.core.logger import logger
from app.modules.auth.schemas.refresh import (
    RefreshTokenRequest,
    RefreshTokenResponse,
)
from app.modules.auth.services.refresh_service import RefreshTokenService

router = APIRouter()


@router.post(
    "",
    response_model=RefreshTokenResponse,
    status_code=200,
    summary="Refresh access token",
)
async def refresh_token(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> RefreshTokenResponse:
    """Revoke old refresh token and return a new access + refresh token pair."""
    logger.info("POST /auth/refresh - Refresh token endpoint called")
    # ── Read refresh token from cookie ─────────────────────────────────
    refresh_token_value = request.cookies.get("refresh_token")
    if refresh_token_value is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token not found in cookies.",
        )

    # ── Extract old access token JTI from Authorization header ─────────
    old_access_token_jti = None
    old_access_token_expires_at = None
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        access_token = auth_header.removeprefix("Bearer ")
        try:
            payload = decode_token(access_token)
            old_access_token_jti = payload.get("jti")
            exp_timestamp = payload.get("exp")
            if exp_timestamp is not None:
                old_access_token_expires_at = datetime.fromtimestamp(
                    exp_timestamp, tz=timezone.utc
                )
        except JWTError:
            # If the access token is already expired, skip blacklisting
            pass

    # ── Extract device info from request ───────────────────────────────
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    # ── Execute refresh ────────────────────────────────────────────────
    body = RefreshTokenRequest(refresh_token=refresh_token_value)
    service = RefreshTokenService(db)
    result = await service.execute(
        body,
        old_access_token_jti=old_access_token_jti,
        old_access_token_expires_at=old_access_token_expires_at,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    # ── Set new refresh token as HttpOnly cookie ───────────────────────
    response.set_cookie(
        key="refresh_token",
        value=result.refresh_token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="strict",
        path="/api/v1/auth/refresh",
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,  # days → seconds
    )

    return result.response
