"""
POST /auth/logout — Revoke refresh token (logout).

Invalidates the provided refresh token so it can no longer be used.
Refresh token is read from an HttpOnly cookie.
"""
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
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
    """Revoke the provided refresh token to log the user out."""
    # Read refresh token from cookie
    refresh_token_value = request.cookies.get("refreshToken")
    if refresh_token_value is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token not found in cookies.",
        )

    body = LogoutRequest(refresh_token=refresh_token_value)
    service = LogoutService(db)
    result = await service.execute(body)

    # Clear the refresh token cookie
    response.delete_cookie(
        key="refreshToken",
        path="/auth/refresh",
    )

    return result