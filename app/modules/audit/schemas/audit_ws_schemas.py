"""
WebSocket message schemas for audit event streaming.
"""
from typing import Any, Literal, Optional
from pydantic import BaseModel, Field


class WSEventData(BaseModel):
    """Base event data."""
    pass


class WSProgressEvent(BaseModel):
    """WebSocket event message for real-time progress updates."""

    type: Literal["event"] = "event"
    event_type: str = Field(..., description="Type of event (e.g., crawl_started, parse_page_complete)")
    audit_id: str = Field(..., description="Audit ID")
    url: str = Field(default="", description="URL related to the event")
    timestamp: str = Field(..., description="ISO timestamp of the event")
    seq: int = Field(..., description="Sequence number for ordering/resume")
    payload: dict[str, Any] = Field(default_factory=dict, description="Event-specific data")
    category: Optional[str] = Field(default=None, description="Category tag (e.g., 'crawl', 'parse', 'evaluate', 'score')")


class WSFinalEvent(BaseModel):
    """WebSocket final snapshot message when pipeline completes."""

    type: Literal["final"] = "final"
    audit_id: str = Field(..., description="Audit ID")
    summary: dict[str, Any] = Field(..., description="Audit summary with scores, counts")
    pages: list[dict[str, Any]] = Field(default_factory=list, description="Per-page results")
    status: str = Field(default="completed", description="Final status")


class WSErrorEvent(BaseModel):
    """WebSocket error message."""

    type: Literal["error"] = "error"
    audit_id: str = Field(..., description="Audit ID")
    message: str = Field(..., description="Error message")
    code: Optional[str] = Field(default=None, description="Error code")


class WSCloseEvent(BaseModel):
    """WebSocket close message."""

    type: Literal["close"] = "close"
    audit_id: str = Field(..., description="Audit ID")
    reason: str = Field(..., description="Close reason")


# Union of all possible WebSocket messages
WSMessage = WSProgressEvent | WSFinalEvent | WSErrorEvent | WSCloseEvent


# Query parameters for WebSocket connection
class WSQueryParams(BaseModel):
    """Query parameters for WebSocket connection."""

    last_id: Optional[str] = Field(default=None, description="Redis stream entry ID to resume from")
    detail: bool = Field(default=False, description="Emit granular RULE_CHECKED events (debug mode)")


__all__ = [
    "WSEventData",
    "WSProgressEvent",
    "WSFinalEvent",
    "WSErrorEvent",
    "WSCloseEvent",
    "WSMessage",
    "WSQueryParams",
]