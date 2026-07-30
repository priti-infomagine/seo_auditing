"""
Schema for user logout.
"""
from pydantic import BaseModel, Field


class LogoutRequest(BaseModel):
    """Logout request body (token is read from cookie by the route)."""

    refresh_token: str = Field(
        ...,
        description="The refresh token to revoke",
    )


class LogoutResponse(BaseModel):
    """Response after successful logout."""

    message: str