"""Schemas for the asynchronous Sitemap check API."""
from typing import List, Literal, Optional
from uuid import UUID
from pydantic import BaseModel, Field, field_validator

from .model import SitemapCheckStatus, SitemapOverallStatus, SitemapSeverity


class SitemapCheckRequest(BaseModel):
    url: str = Field(
        ...,
        min_length=1,
        description="Website URL or bare domain to check (e.g. example.com, https://example.com)",
    )

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("url must not be empty")
        return normalized


class SitemapCheckQueuedResponse(BaseModel):
    """Returned immediately upon queuing the check (HTTP 202)."""
    check_id: UUID = Field(..., description="Unique check identifier")
    task_id: Optional[str] = Field(None, description="Celery background task ID")
    url: str = Field(..., description="Target URL")
    domain: str = Field(..., description="Normalized domain")
    status: SitemapCheckStatus = Field(
        default=SitemapCheckStatus.QUEUED, description="Current check status"
    )
    created_at: Optional[str] = Field(None, description="ISO timestamp of creation")


class SitemapIssue(BaseModel):
    """Issue detected for a sitemap or domain."""
    code: str = Field(..., description="Stable issue identifier code")
    severity: Literal["none", "low", "medium", "high", "critical"] = Field(
        ..., description="Issue severity"
    )
    status: Literal["pass", "warning", "fail"] = Field(
        default="warning", description="Status classification"
    )
    message: str = Field(..., description="Human-readable issue description")
    evidence: Optional[str] = Field(None, description="Supporting evidence")


class SitemapRecommendation(BaseModel):
    """Actionable fix recommendation."""
    code: str = Field(..., description="Associated issue code")
    priority: Literal["critical", "high", "medium", "low", "info"] = Field(
        ..., description="Fix priority"
    )
    title: str = Field(..., description="Short recommendation title")
    message: str = Field(..., description="Detailed explanation")
    fix: str = Field(..., description="Actionable fix instruction")
    where_to_fix: Literal[
        "sitemap_xml", "robots_txt", "server_config", "cms", "cdn", "dns"
    ] = Field(..., description="Where to apply the fix")
    evidence: Optional[str] = Field(None, description="Context / evidence")


class SitemapFileItem(BaseModel):
    """Individual sitemap file audit result."""
    url: str = Field(..., description="Sitemap URL")
    is_index: bool = Field(default=False, description="Whether this is a sitemap index")
    status_code: int = Field(..., description="HTTP status code")
    content_type: str = Field(..., description="Content-Type header")
    entry_count: int = Field(..., description="Number of entries in this sitemap")
    content_length: int = Field(default=0, description="Size in bytes")
    response_time_ms: int = Field(default=0, description="Response time in milliseconds")
    error: Optional[str] = Field(None, description="Fetch or parse error if any")
    issues: List[SitemapIssue] = Field(
        default_factory=list, description="Issues specific to this sitemap file"
    )
    recommendations: List[SitemapRecommendation] = Field(
        default_factory=list, description="Recommendations for this file"
    )


class SitemapSummary(BaseModel):
    """High-level summary of sitemap discovery and health."""
    total_sitemaps: int = Field(0, description="Total sitemap files discovered")
    sitemap_indexes: int = Field(0, description="Total sitemap index files")
    url_sitemaps: int = Field(0, description="Total standard URL sitemaps")
    total_urls_declared: int = Field(0, description="Total page URLs declared across sitemaps")
    total_issues: int = Field(0, description="Total issues detected")


class SitemapCheckResultResponse(BaseModel):
    """Complete sitemap audit result payload."""
    check_id: UUID
    url: str
    domain: str
    status: SitemapCheckStatus
    checked_at: Optional[str] = None
    overall_status: Optional[str] = None
    severity: Optional[str] = None
    summary: Optional[SitemapSummary] = None
    sitemaps: List[SitemapFileItem] = Field(default_factory=list)
    findings: List[SitemapIssue] = Field(default_factory=list)
    recommendations: List[SitemapRecommendation] = Field(default_factory=list)
    cost_seconds: Optional[float] = None


class SitemapCheckStatusResponse(BaseModel):
    """Response returned when polling /status/{check_id}."""
    check_id: UUID
    url: str
    domain: str
    status: SitemapCheckStatus
    progress: Optional[dict] = None
    error: Optional[str] = None
