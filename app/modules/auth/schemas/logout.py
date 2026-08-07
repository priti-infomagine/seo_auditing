"""
Schema for user logout.
"""
from pydantic import BaseModel, Field


class LogoutRequest(BaseModel):
    """Logout request body."""

    refresh_token: str = Field(
        ...,
        description="The refresh token to revoke",
    )
    access_token: str = Field(
        ...,
        description="Access token to blacklist by JTI",
    )


class LogoutResponse(BaseModel):
    """Response after successful logout."""

    message: str