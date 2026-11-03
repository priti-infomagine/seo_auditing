"""
Request/Response schemas for Contact Us API.
"""
import re

from pydantic import BaseModel, EmailStr, Field, HttpUrl, field_validator


class ContactRequest(BaseModel):
    """Contact form request body."""

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
    website: HttpUrl | None = Field(
        None,
        description="User's website URL (optional)",
    )
    topic: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Contact topic/subject",
    )
    message: str = Field(
        ...,
        min_length=10,
        max_length=5000,
        description="Contact message content",
    )

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

    @field_validator("topic")
    @classmethod
    def validate_topic(cls, v: str) -> str:
        """Topic must not be empty after stripping."""
        stripped = v.strip()
        if not stripped:
            raise ValueError("Topic cannot be empty.")
        return stripped

    @field_validator("message")
    @classmethod
    def validate_message(cls, v: str) -> str:
        """Message must not be empty after stripping."""
        stripped = v.strip()
        if not stripped:
            raise ValueError("Message cannot be empty.")
        if len(stripped) < 10:
            raise ValueError("Message must be at least 10 characters long.")
        return stripped


class ContactResponse(BaseModel):
    """Response after successful contact form submission."""

    message: str = "Your message has been sent successfully"