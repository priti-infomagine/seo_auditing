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
    max_depth: int = Field(default=3, ge=1, le=10, description="Maximum link traversal depth")
    audit_id: str | None = Field(default=None, description="Optional pre-assigned audit ID")


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
    crawled_pages: int = 0
    overall_score: float | None = None
    grade: str | None = None
    events: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Recent events emitted during the audit pipeline",
    )


class RuleResultSchema(BaseModel):
    """Schema for a single rule result in a page response."""

    model_config = ConfigDict(from_attributes=True)

    rule_id: str
    rule_name: str
    category: str
    passed: bool
    severity: str
    message: str
    recommendation: str | None = None
    score_impact: float = 0.0
    data: dict[str, Any] = Field(default_factory=dict)


class PageScoreSchema(BaseModel):
    """Schema for a single page score in an audit response."""

    model_config = ConfigDict(from_attributes=True)

    url: str
    score: float
    overall_score: float
    grade: str
    on_page_score: float
    technical_score: float
    total_rules: int
    passed: int
    failed: int
    rules: list[RuleResultSchema] = Field(default_factory=list)


class CategoryScoreSchema(BaseModel):
    """Schema for a category score."""

    model_config = ConfigDict(from_attributes=True)

    category: str
    score: float
    weight: float
    rules_checked: int
    passed_rules: int


class AuditReportResponse(BaseModel):
    """Full audit report response."""

    model_config = ConfigDict(from_attributes=True)

    audit_id: str
    status: str
    start_url: str | None = None
    overall_score: float
    grade: str
    total_pages: int
    crawled_pages: int
    categories: list[CategoryScoreSchema] = Field(default_factory=list)
    pages: list[PageScoreSchema] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


# Backwards-compatible alias from original schema
class RequestSchema(BaseModel):
    """Legacy alias for request schema."""

    model_config = ConfigDict(from_attributes=True)

    url: str = Field(..., min_length=1, description="The URL to crawl")
    max_pages: int = Field(default=10, ge=1, lt=20, description="Maximum pages to crawl")


__all__ = [
    "AuditConfig",
    "AuditReportResponse",
    "CategoryScoreSchema",
    "CrawlStartedResponse",
    "CrawlStatusResponse",
    "PageScoreSchema",
    "RequestSchema",
    "RuleResultSchema",
]
