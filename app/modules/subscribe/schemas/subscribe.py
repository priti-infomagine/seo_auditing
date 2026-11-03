"""
Request/Response schemas for Subscribe API.
"""
from pydantic import BaseModel, EmailStr, Field


class SubscribeRequest(BaseModel):
    """Subscribe request body."""
    email: EmailStr = Field(..., description="Subscriber's email address")


class SubscribeResponse(BaseModel):
    """Response after successful subscription."""
    message: str = "Thanks for subscribing! We'll send you updates and new product launches."