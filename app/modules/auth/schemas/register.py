"""
Request schema for user registration.
"""
import re

from pydantic import BaseModel, EmailStr, Field, field_validator


class RegisterRequest(BaseModel):
    """Registration request body."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="User's full name",
    )
    email: EmailStr = Field(
        ...,
        description="User's email address",
    )
    password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="Password (min 8 characters, must contain at least 1 uppercase letter, 1 digit, and 1 special character)",
    )

    # ── Name validation ──────────────────────────────────────────────
    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Name must not contain digits or special characters.

        Allowed: letters (a-z, A-Z), spaces, hyphens, and apostrophes
        (to support names like "O'Brien" or double-barrelled names).
        """
        if not re.match(r"^[A-Za-zÀ-ÿ' \-]+$", v):
            raise ValueError(
                "Name must contain only letters, spaces, hyphens, or apostrophes "
                "(no digits or special characters)."
            )
        return v.strip()

    # ── Password strength validation ─────────────────────────────────
    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        """Enforce password strength rules.

        * At least 1 uppercase letter (A-Z)
        * At least 1 digit (0-9)
        * At least 1 special character (non-alphanumeric)
        * Minimum length of 8 (enforced by Field)
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


class RegisterResponse(BaseModel):
    """Response after successful registration (OTP sent)."""

    message: str