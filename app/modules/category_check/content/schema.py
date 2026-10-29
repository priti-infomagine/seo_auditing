"""
Pydantic schemas for the Content crawler API layer.

Mirrors core_seo's schema.py but for content-specific response models.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.modules.category_check.core_seo.schema import RuleResultSchema


class ContentAuditConfig(BaseModel):
    """Request body for starting a Content audit."""

    model_config = ConfigDict(from_attributes=True)

    url: str = Field(..., description="The start URL to audit", min_length=1)
    max_pages: int = Field(default=10, ge=1, le=100, description="Maximum pages to crawl")


class ContentCrawlStartedResponse(BaseModel):
    """Response returned when a content crawl/audit is started."""

    model_config = ConfigDict(from_attributes=True)

    audit_id: str = Field(..., description="Unique audit identifier")
    status: str = Field(..., description="Initial status (always 'started')")
    message: str = Field(default="Content crawl started successfully", description="Status message")


class ContentCrawlStatusResponse(BaseModel):
    """Response for polling content audit status."""

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
    events: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Recent events emitted during the content audit pipeline",
    )


class ContentRuleResultSchema(RuleResultSchema):
    """Schema for a single content rule result."""


class ContentPageScoreSchema(BaseModel):
    """Schema for a single page score in a content audit response."""

    model_config = ConfigDict(from_attributes=True)

    url: str
    status: str = "completed"
    passed: int = 0
    failed: int = 0
    total: int = 0
    pass_percentage: float = 0.0
    results: list[RuleResultSchema] = Field(default_factory=list)


class ContentAuditReportResponse(BaseModel):
    """Full content audit report response."""

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
    pages: list[ContentPageScoreSchema] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


__all__ = [
    "ContentAuditConfig",
    "ContentCrawlStartedResponse",
    "ContentCrawlStatusResponse",
    "ContentAuditReportResponse",
    "ContentRuleResultSchema",
    "ContentPageScoreSchema",
    "RuleResultSchema",
]
