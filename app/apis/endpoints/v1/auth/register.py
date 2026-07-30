"""
POST /auth/register — Register a new user.

Sends OTP to user's email for verification.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.auth_schemas.register import RegisterRequest, RegisterResponse
from app.services.auth_services.register_service import RegisterService

router = APIRouter()


@router.post(
    "",
    response_model=RegisterResponse,
    status_code=201,
    summary="Register a new user",
)
async def register(
    body: RegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> RegisterResponse:
    """Create a new user account and send OTP for email verification."""
    service = RegisterService(db)
    return await service.execute(body)