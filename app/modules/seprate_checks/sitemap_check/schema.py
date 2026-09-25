"""Schemas for the sitemap single-check API."""
from typing import Optional
from urllib.parse import urlparse
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class SitemapCheckRequest(BaseModel):
    url: str = Field(
        ...,
        description="Website URL whose robots.txt and sitemap files should be checked",
    )

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        normalized = value.strip()
        parsed = urlparse(normalized)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("url must be an absolute http or https URL")
        return normalized.rstrip("/")


class SitemapFinding(BaseModel):
    code: str = Field(..., description="Stable finding identifier")
    severity: str = Field(..., description="none | low | medium | high | critical")
    status: str = Field(..., description="pass | warning | fail | not_applicable")
    message: str = Field(..., description="What was detected")
    evidence: str = Field(..., description="Evidence from the checked sitemap files")
    recommendation: str = Field(..., description="How to fix the finding")


class SitemapRecommendation(BaseModel):
    code: str
    priority: str
    title: str
    message: str
    evidence: list[str] = Field(default_factory=list)
    fix: str


class SitemapRobotsSummary(BaseModel):
    url: str
    exists: bool
    status_code: Optional[int] = None
    sitemap_references: list[str] = Field(default_factory=list)


class SitemapCheckSummary(BaseModel):
    status: str
    severity: str
    sitemap_files: int
    sitemap_indexes: int
    url_sets: int
    page_urls: int
    passed_checks: int
    warning_count: int
    failure_count: int


class SitemapFileResult(BaseModel):
    url: str
    status_code: Optional[int] = None
    exists: bool = False
    is_index: bool = False
    content_type: Optional[str] = None
    content_length: int = 0
    child_sitemaps: list[str] = Field(default_factory=list)
    url_count: int = 0
    urls: list[str] = Field(default_factory=list)
    raw_content: Optional[str] = None
    error: Optional[str] = None
    kind: str = "urlset"
    health: str = "unknown"
    issues: list[str] = Field(default_factory=list)
    duplicate_url_count: int = 0
    invalid_url_count: int = 0
    cross_host_url_count: int = 0


class SitemapCheckResponse(BaseModel):
    checked_url: str
    robots_url: str
    robots_status_code: Optional[int] = None
    robots_sitemap_references: list[str] = Field(default_factory=list)
    sitemap_files: list[SitemapFileResult] = Field(default_factory=list)
    total_sitemap_files: int = 0
    total_page_urls: int = 0
    findings: list[SitemapFinding] = Field(default_factory=list)
    overall_status: str
    severity: str
    recommendations: list[str] = Field(default_factory=list)
    recommendation_items: list[SitemapRecommendation] = Field(default_factory=list)
    summary: SitemapCheckSummary
    robots: SitemapRobotsSummary
    report_markdown: str


class SitemapCheckAcceptedResponse(BaseModel):
    check_id: UUID
    checked_url: str
    status: str
    summary: SitemapCheckSummary
    robots: SitemapRobotsSummary
    findings: list[SitemapFinding] = Field(default_factory=list)
    recommendation_items: list[SitemapRecommendation] = Field(default_factory=list)
    files_url: str


class SitemapFilePageItem(BaseModel):
    index: int
    url: str
    kind: str
    health: str
    status_code: Optional[int] = None
    content_type: Optional[str] = None
    content_length: int = 0
    url_count: int = 0
    child_sitemap_count: int = 0
    issues: list[str] = Field(default_factory=list)
    error: Optional[str] = None


class SitemapFilePage(BaseModel):
    items: list[SitemapFilePageItem]
    page: int
    page_size: int
    total: int
    has_next: bool


class SitemapUrlPage(BaseModel):
    sitemap_url: str
    items: list[str]
    page: int
    page_size: int
    total: int
    has_next: bool


class SitemapRawResponse(BaseModel):
    sitemap_url: str
    content_type: Optional[str] = None
    content_length: int = 0
    raw_content: Optional[str] = None
