"""
Schemas for OTP verification and auto-login after verification.
"""
from pydantic import BaseModel, EmailStr, Field


class VerifyOTPRequest(BaseModel):
    """OTP verification request body."""

    email: EmailStr = Field(
        ...,
        description="User's email address",
    )
    otp: str = Field(
        ...,
        min_length=6,
        max_length=6,
        description="6-digit OTP",
    )


class VerifyOTPResponse(BaseModel):
    """Response after successful OTP verification (auto-login)."""

    message: str
    access_token: str
    token_type: str = "bearer"