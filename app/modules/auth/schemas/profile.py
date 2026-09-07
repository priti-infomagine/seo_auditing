"""
Schemas for user profile endpoints.

Endpoints:
    GET /user/profile → Get current user's profile
"""
from pydantic import BaseModel, EmailStr ,ConfigDict


class UserProfileResponse(BaseModel):
    id: str
    name: str
    email: EmailStr
    plan: str
    credits: int
    is_verified: bool

    model_config = ConfigDict(from_attributes=True)
