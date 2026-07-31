"""
POST /auth/logout — Revoke refresh token and blacklist access token.

Steps:
    1. Read refresh token from HttpOnly cookie
    2. Extract access token from Authorization header
    3. Decode access token and get JTI + expiry
    4. Revoke refresh token
    5. Blacklist access token
    6. Delete refresh token cookie
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.jwt import decode_token
from app.core.logger import logger
from app.schemas.auth_schemas.logout import LogoutRequest, LogoutResponse
from app.services.auth_services.logout_service import LogoutService


router = APIRouter()


@router.post(
    "",
    response_model=LogoutResponse,
    status_code=200,
    summary="Logout and revoke refresh token",
)
async def logout(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> LogoutResponse:
    """
    Logout user by revoking refresh token and blacklisting access token.
    """

    logger.info("POST /auth/logout - Logout endpoint called")

    # ── 1. Read refresh token from HttpOnly cookie ─────────────────────
    refresh_token = request.cookies.get("refreshToken")

    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token not found.",
        )

    # ── 2. Extract access token from Authorization header ───────────────
    access_token_jti: str | None = None
    access_token_expires_at: datetime | None = None

    auth_header = request.headers.get("Authorization")

    if auth_header and auth_header.startswith("Bearer "):
        access_token = auth_header.removeprefix("Bearer ").strip()

        try:
            payload = decode_token(access_token)

            access_token_jti = payload.get("jti")

            exp_timestamp = payload.get("exp")

            if exp_timestamp:
                access_token_expires_at = datetime.fromtimestamp(
                    exp_timestamp,
                    tz=timezone.utc,
                )

        except JWTError:
            # Access token invalid/expired.
            # Refresh token logout can continue.
            logger.info(
                "Access token could not be decoded during logout"
            )

    # ── 3. Execute logout service ──────────────────────────────────────
    service = LogoutService(db)

    result = await service.execute(
        LogoutRequest(refresh_token=refresh_token),
        access_token_jti=access_token_jti,
        access_token_expires_at=access_token_expires_at,
    )

    # ── 4. Remove refresh token cookie ─────────────────────────────────
    response.delete_cookie(
        key="refreshToken",
        path="/",
    )

    logger.info("User logged out successfully")

    return result
