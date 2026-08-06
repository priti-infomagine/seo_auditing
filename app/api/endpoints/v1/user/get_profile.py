"""
GET /user/profile — Get current authenticated user's profile.

Security:
    Requires a valid Bearer access token.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.logger import logger
from app.core.security import get_current_user
from app.modules.auth.models.users import User
from app.modules.auth.schemas.profile import UserProfileResponse
from app.modules.auth.services.profile_service import GetProfileService

router = APIRouter()


@router.get(
    "/profile",
    response_model=UserProfileResponse,
    status_code=200,
    summary="Get current user profile",
)
async def get_profile(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserProfileResponse:
    """Return the authenticated user's profile information."""
    logger.info("GET /user/profile - Get profile endpoint called")
    service = GetProfileService(db)
    return await service.execute(current_user)
