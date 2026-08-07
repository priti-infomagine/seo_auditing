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
from app.modules.auth.utils.auth_utils import decode_token
from app.core.logger import logger
from app.modules.auth.schemas.logout import LogoutRequest, LogoutResponse
from app.modules.auth.services.logout_service import LogoutService


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
    refresh_token = request.cookies.get("refresh_token")

    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token not found.",
        )

    # ── 2. Extract access token from Authorization header or request body ──
    auth_header = request.headers.get("Authorization")

    if auth_header and auth_header.startswith("Bearer "):
        access_token = auth_header.removeprefix("Bearer ").strip()
    else:
        try:
            body = await request.json()
            access_token = body.get("access_token") if isinstance(body, dict) else None
        except Exception:
            access_token = None

    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Access token is required for logout.",
        )

    try:
        payload = decode_token(access_token)
        access_token_jti = payload.get("jti")
        exp_timestamp = payload.get("exp")
        access_token_expires_at = (
            datetime.fromtimestamp(exp_timestamp, tz=timezone.utc)
            if exp_timestamp
            else None
        )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token.",
        )

    # ── 3. Execute logout service ──────────────────────────────────────
    service = LogoutService(db)

    result = await service.execute(
        LogoutRequest(refresh_token=refresh_token, access_token=access_token),
        access_token_jti=access_token_jti,
        access_token_expires_at=access_token_expires_at,
    )

    # ── 4. Remove refresh token cookie ─────────────────────────────────
    response.delete_cookie(
        key="refresh_token",
        path="/",
    )

    logger.info("User logged out successfully")

    return result
