"""
Schemas for the combined crawl + parse + score (full audit) API endpoint.

The audit endpoints (analyze / score / result) now return the unified response
shape defined in audit_response_schemas.UnifiedAuditResponse. The legacy
AuditAnalyzeResponse / SeoAnalysisResponse names are kept as aliases for import
backward-compatibility.
"""
from uuid import UUID

from app.core.config import settings
from pydantic import BaseModel, Field, field_validator
from typing import Optional, Dict, Any, List

from app.modules.audit.schemas.audit_response_schemas import UnifiedAuditResponse


class AuditRequest(BaseModel):
    """Request schema for running a combined crawl + parse audit."""

    url: str = Field(
        ...,
        description="URL or website name to audit (e.g., 'https://example.com' or 'example.com')",
        examples=["https://example.com"]
    )
    deep_crawl: bool = Field(
        False,
        description="Mock flag: whether to simulate a deep crawl (more pages/resources)",
        examples=[False]
    )

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        """Validate URL format."""
        url = v.strip()
        if not url:
            raise ValueError("URL cannot be empty")

        # Auto-prepend https:// if no protocol
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"

        return url


class MockCrawlResult(BaseModel):
    """Mock result of the crawling phase."""

    status_code: int = Field(..., description="Mock HTTP status code")
    html_size_bytes: int = Field(..., description="Mock HTML size in bytes")
    response_time_ms: float = Field(..., description="Mock response time in milliseconds")
    pages_crawled: int = Field(..., description="Mock number of pages crawled")


class MockParseResult(BaseModel):
    """Mock result of the parsing phase."""

    title: str = Field(..., description="Mock extracted page title")
    meta_description: str = Field(..., description="Mock extracted meta description")
    word_count: int = Field(..., description="Mock extracted word count")
    total_links: int = Field(..., description="Mock extracted link count")
    total_images: int = Field(..., description="Mock extracted image count")
    seo_score: int = Field(..., description="Mock calculated SEO score (0-100)")
    seo_grade: str = Field(..., description="Mock SEO grade (A-F)")


class AuditResponse(BaseModel):
    """Response schema for the combined crawl + parse audit."""

    success: bool = Field(..., description="Whether the audit was successful")
    message: str = Field(..., description="Status message")
    url: str = Field(..., description="The audited URL")
    domain: str = Field(..., description="Extracted domain name")
    crawl: MockCrawlResult = Field(..., description="Mock crawl phase result")
    parse: MockParseResult = Field(..., description="Mock parse phase result")
    mock: bool = Field(True, description="Indicates this is a mock API result")


class AuditError(BaseModel):
    """Error response schema."""

    success: bool = False
    error: str = Field(..., description="Error type")
    detail: str = Field(..., description="Error details")


class AuditAnalyzeRequest(BaseModel):
    """Request schema for running a complete crawl → parse → score audit."""

    url: str = Field(
        ...,
        description="URL or website name to audit (e.g., 'https://example.com' or 'example.com')",
        examples=["https://example.com"]
    )
    max_pages: Optional[int] = Field(
        default=None,
        ge=1,
        description="Maximum number of pages to crawl and analyze. If not provided, uses CrawlConfig default (from .env or code).",
    )
    max_depth: Optional[int] = Field(
        default=None,
        ge=0,
        le=10,
        description="Maximum link depth from the start URL to follow. If not provided, uses CrawlConfig default (5).",
        examples=[5],
    )
    concurrency: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Number of concurrent crawl workers",
    )
    project_id: Optional[UUID] = Field(
        default=None,
        description="Optional existing project ID to group this audit under. If omitted, a new project is created.",
    )

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        """Validate URL format."""
        url = v.strip()
        if not url:
            raise ValueError("URL cannot be empty")

        # Auto-prepend https:// if no protocol
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"

        return url


class CrawlSummarySchema(BaseModel):
    """Summary of crawl phase."""

    url: str
    domain: str
    status_code: int
    response_time: float
    html_size_bytes: int
    test_number: int
    file_path: str
    crawled_at: str
    pages_discovered: int = Field(default=1, description="Total pages discovered during crawl")
    pages_crawled: int = Field(default=1, description="Total pages successfully crawled")


class AuditAnalyzeError(BaseModel):
    """Error response schema."""

    success: bool = False
    error: str = Field(..., description="Error type")
    detail: str = Field(..., description="Error details")


class AuditAnalyzeQueuedResponse(BaseModel):
    """
    Response for a queued (async) audit request.

    POST /audit/analyze enqueues a Celery task and returns immediately with
    the identifiers needed to poll for progress and fetch the final result.
    """

    success: bool = Field(..., description="Whether the audit was successfully queued")
    status: str = Field(..., description="Queued status, e.g. 'queued'")
    message: str = Field(..., description="Human-readable status message")
    url: str = Field(..., description="The audited URL")
    domain: str = Field(..., description="Extracted domain name")
    crawl_id: str = Field(..., description="Crawl job ID (also the analysis grouping key)")
    project_id: str = Field(..., description="Project ID tracking this audit")
    task_id: str = Field(..., description="Celery task ID for the crawl (poll for progress)")
    task_status_url: str = Field(..., description="URL to poll the crawl task state")
    crawl_status_url: str = Field(..., description="URL to fetch crawl job status")
    pipeline_status_url: str = Field(..., description="URL to fetch pipeline stage status")
    result_url: str = Field(..., description="URL to fetch the final analysis result")


# Unified response shape (audit, summary, categories, issues, ...).
# Kept as an alias so existing imports `from audit_schemas import AuditAnalyzeResponse`
# continue to resolve to the unified response model.
AuditAnalyzeResponse = UnifiedAuditResponse

