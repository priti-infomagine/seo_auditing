"""
Service layer for user profile operations.

Endpoints:
    GET /user/profile → Get current user's profile
"""
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models.users import User
from app.modules.auth.schemas.profile import UserProfileResponse


class GetProfileService:
    """Fetch the authenticated user's profile."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def execute(self, current_user: User) -> UserProfileResponse:
        try:
            return UserProfileResponse(
                id=str(current_user.id),
                name=current_user.name,
                email=current_user.email,
                plan=current_user.plan,
                credits=current_user.credits,
                is_verified=current_user.is_verified,
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"An unexpected error occurred: {str(e)}",
            )