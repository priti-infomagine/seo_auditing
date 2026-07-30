"""
Schemas for refresh token renewal.
"""
from pydantic import BaseModel, Field


class RefreshTokenRequest(BaseModel):
    """Refresh token request body (token is read from cookie by the route)."""

    refresh_token: str = Field(
        ...,
        description="The refresh token to renew",
    )


class RefreshTokenResponse(BaseModel):
    """Response with new access token."""

    access_token: str
    token_type: str = "bearer"