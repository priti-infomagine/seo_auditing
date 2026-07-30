"""
POST /auth/login — Authenticate a verified user.

Returns JWT access + refresh tokens.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.auth_schemas.login import LoginRequest, LoginResponse
from app.services.auth_services.login_service import LoginService

router = APIRouter()


@router.post(
    "",
    response_model=LoginResponse,
    status_code=200,
    summary="Login with email and password",
)
async def login(
    body: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> LoginResponse:
    """Authenticate a verified user and return JWT tokens."""
    service = LoginService(db)
    return await service.execute(body)