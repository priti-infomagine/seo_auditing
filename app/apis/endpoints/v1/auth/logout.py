"""
POST /auth/logout — Revoke refresh token and blacklist access token (logout).

Invalidates the provided refresh token and blacklists the access token
so it can no longer be used for API requests.
Refresh token is read from an HttpOnly cookie.
Access token is read from the Authorization header.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.jwt import decode_token
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
    """Revoke the provided refresh token and blacklist the access token."""
    # ── Read refresh token from cookie ─────────────────────────────────
    refresh_token_value = request.cookies.get("refreshToken")
    if refresh_token_value is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token not found in cookies.",
        )

    # ── Extract access token from Authorization header ─────────────────
    access_token_jti = None
    access_token_expires_at = None
    
    # DEBUG: Print the raw Authorization header
    auth_header = request.headers.get("Authorization")
    print(f"[DEBUG LOGOUT] Authorization header: {auth_header}")
    
    if auth_header and auth_header.startswith("Bearer "):
        access_token = auth_header.removeprefix("Bearer ")
        print(f"[DEBUG LOGOUT] Extracted access token: {access_token[:20]}...")
        try:
            payload = decode_token(access_token)
            print(f"[DEBUG LOGOUT] Decoded payload keys: {list(payload.keys())}")
            
            access_token_jti = payload.get("jti")
            print(f"[DEBUG LOGOUT] Extracted JTI: {access_token_jti}")
            
            exp_timestamp = payload.get("exp")
            print(f"[DEBUG LOGOUT] Extracted exp timestamp: {exp_timestamp}")
            
            if exp_timestamp is not None:
                access_token_expires_at = datetime.fromtimestamp(
                    exp_timestamp, tz=timezone.utc
                )
                print(f"[DEBUG LOGOUT] Converted exp to datetime: {access_token_expires_at}")
        except JWTError as e:
            # If the access token is already expired, we can skip blacklisting
            print(f"[DEBUG LOGOUT] JWTError decoding access token: {e}")
            pass
    else:
        print(f"[DEBUG LOGOUT] No Bearer token found in Authorization header")

    print(f"[DEBUG LOGOUT] Final values - JTI: {access_token_jti}, exp: {access_token_expires_at}")

    # ── Execute logout ─────────────────────────────────────────────────
    body = LogoutRequest(refresh_token=refresh_token_value)
    service = LogoutService(db)
    result = await service.execute(
        body,
        access_token_jti=access_token_jti,
        access_token_expires_at=access_token_expires_at,
    )

    # ── Clear the refresh token cookie ─────────────────────────────────
    response.delete_cookie(
        key="refreshToken",
        path="/",
    )

    return result
