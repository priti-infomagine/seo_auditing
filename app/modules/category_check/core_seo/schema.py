"""
Pydantic schemas for the Core SEO crawler API layer.

Schemas:
    AuditConfig          — request body for POST /crawl
    CrawlStartedResponse — response for POST /crawl
    CrawlStatusResponse  — response for GET /status/{audit_id}
    AuditReportResponse  — full audit report response
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AuditConfig(BaseModel):
    """Request body for starting a Core SEO audit."""

    model_config = ConfigDict(from_attributes=True)

    url: str = Field(..., description="The start URL to audit", min_length=1)
    max_pages: int = Field(default=10, ge=1, le=100, description="Maximum pages to crawl")


class CrawlStartedResponse(BaseModel):
    """Response returned when a crawl/audit is started."""

    model_config = ConfigDict(from_attributes=True)

    audit_id: str = Field(..., description="Unique audit identifier")
    status: str = Field(..., description="Initial status (always 'started')")
    message: str = Field(default="Crawl started successfully", description="Status message")


class CrawlStatusResponse(BaseModel):
    """Response for polling audit status."""

    model_config = ConfigDict(from_attributes=True)

    audit_id: str
    status: str
    start_url: str | None = None
    total_pages: int = 0
    pages_done: int = 0
    pages_failed: int = 0
    rules_passed: int = 0
    rules_failed: int = 0
    pass_percentage: float = 0.0
    content_pages_done: int = 0
    content_pages_failed: int = 0
    content_rules_passed: int = 0
    content_rules_failed: int = 0
    content_pass_percentage: float = 0.0
    events: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Recent events emitted during the audit pipeline",
    )


class RuleResultSchema(BaseModel):
    """Schema for a single rule result in a page response."""

    model_config = ConfigDict(from_attributes=True)

    rule_id: str
    name: str
    passed: bool
    severity: str
    message: str
    recommendation: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class PageScoreSchema(BaseModel):
    """Schema for a single page score in an audit response."""

    model_config = ConfigDict(from_attributes=True)

    url: str
    status: str = "completed"
    passed: int = 0
    failed: int = 0
    total: int = 0
    pass_percentage: float = 0.0
    results: list[RuleResultSchema] = Field(default_factory=list)


class AuditReportResponse(BaseModel):
    """Full audit report response."""

    model_config = ConfigDict(from_attributes=True)

    audit_id: str
    status: str
    start_url: str | None = None
    total_pages: int
    crawled_pages: int
    pages_done: int
    pages_failed: int
    rules_passed: int
    rules_failed: int
    pass_percentage: float
    pages: list[PageScoreSchema] = Field(default_factory=list)
    content_pages: list[PageScoreSchema] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    content_rules_passed: int = 0
    content_rules_failed: int = 0
    content_pass_percentage: float = 0.0


# Backwards-compatible alias from original schema
class RequestSchema(BaseModel):
    """Legacy alias for request schema."""

    model_config = ConfigDict(from_attributes=True)

    url: str = Field(..., min_length=1, description="The URL to crawl")
    max_pages: int = Field(default=10, ge=1, lt=20, description="Maximum pages to crawl")


__all__ = [
    "AuditConfig",
    "AuditReportResponse",
    "CrawlStartedResponse",
    "CrawlStatusResponse",
    "PageScoreSchema",
    "RequestSchema",
    "RuleResultSchema",
]
