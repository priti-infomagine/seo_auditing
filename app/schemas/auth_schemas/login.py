"""
Schemas for user login.
"""
import re

from pydantic import BaseModel, EmailStr, Field, field_validator


class LoginRequest(BaseModel):
    """Login request body."""

    email: EmailStr = Field(
        ...,
        description="User's email address",
    )
    password: str = Field(
        ...,
        min_length=1,
        description="User's password",
    )

    # ── Password strength validation ─────────────────────────────────
    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        """Enforce password strength rules.

        * At least 1 uppercase letter (A-Z)
        * At least 1 digit (0-9)
        * At least 1 special character (non-alphanumeric)
        """
        if not re.search(r"[A-Z]", v):
            raise ValueError(
                "Password must contain at least one uppercase letter."
            )
        if not re.search(r"[0-9]", v):
            raise ValueError(
                "Password must contain at least one digit."
            )
        if not re.search(r"[^A-Za-z0-9]", v):
            raise ValueError(
                "Password must contain at least one special character "
                "(e.g. !@#$%^&*)."
            )
        return v


class LoginResponse(BaseModel):
    """Response after successful login."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"