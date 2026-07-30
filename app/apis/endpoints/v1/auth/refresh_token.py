"""
POST /auth/refresh — Refresh access token using refresh token (rotation).

Revokes old refresh token and issues a new pair.
Refresh token is read from an HttpOnly cookie, and the new one is set as a cookie.
"""
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.schemas.auth_schemas.refresh import (
    RefreshTokenRequest,
    RefreshTokenResponse,
)
from app.services.auth_services.refresh_service import RefreshTokenService

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
    # Read refresh token from cookie
    refresh_token_value = request.cookies.get("refreshToken")
    if refresh_token_value is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token not found in cookies.",
        )

    body = RefreshTokenRequest(refresh_token=refresh_token_value)
    service = RefreshTokenService(db)
    result = await service.execute(body)

    # Set new refresh token as HttpOnly cookie
    response.set_cookie(
        key="refreshToken",
        value=result.refresh_token,
        httponly=True,
        secure=True,
        samesite="strict",
        path="/",
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,  # days → seconds
    )

    return result.response