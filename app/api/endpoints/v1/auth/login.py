"""
POST /auth/login — Authenticate a verified user.

Returns JWT access + refresh tokens with device info stored.
"""
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.logger import logger
from app.modules.auth.schemas.login import LoginRequest, LoginResponse
from app.modules.auth.services.login_service import LoginService

router = APIRouter()


@router.post(
    "",
    response_model=LoginResponse,
    status_code=200,
    summary="Login with email and password",
)
async def login(
    request: Request,
    body: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> LoginResponse:
    """Authenticate a verified user and return JWT tokens."""
    logger.info("POST /auth/login - Login endpoint called")
    # Extract device info from request
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    service = LoginService(db)
    return await service.execute(
        body,
        ip_address=ip_address,
        user_agent=user_agent,
    )
