"""Schemas for the sitemap single-check API - Simplified format."""
from typing import Optional, List, Literal
from pydantic import BaseModel, Field, field_validator
from uuid import UUID


class SitemapCheckRequest(BaseModel):
    url: str = Field(
        ...,
        min_length=1,
        description="Website URL or bare domain to check (e.g. example.com, https://example.com/path)",
    )

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("url must not be empty")
        return normalized


class SitemapIssue(BaseModel):
    """Issue detected for a sitemap."""
    code: str = Field(..., description="Stable issue identifier")
    severity: Literal["none", "low", "medium", "high", "critical"] = Field(..., description="Issue severity")
    message: str = Field(..., description="Human-readable issue description")
    evidence: str = Field(..., description="Evidence from the checked sitemap")


class SitemapRecommendation(BaseModel):
    """Recommendation to fix an issue."""
    code: str = Field(..., description="Links to issue code")
    priority: Literal["critical", "high", "medium", "low", "info"] = Field(..., description="Fix priority")
    title: str = Field(..., description="Short recommendation title")
    message: str = Field(..., description="Detailed recommendation message")
    fix: str = Field(..., description="Actionable fix instruction")
    where_to_fix: Literal["sitemap_xml", "robots_txt", "server_config", "cms", "cdn", "dns"] = Field(
        ..., description="Where to apply the fix"
    )


class SitemapEntry(BaseModel):
    """Individual sitemap file result."""
    url: str = Field(..., description="Sitemap URL that was checked")
    status: int = Field(..., description="HTTP status code")
    contentType: str = Field(..., description="Content-Type header value")
    entries: int = Field(..., description="Number of URL entries in sitemap (0 for index)")
    isIndex: bool = Field(default=False, description="Whether this is a sitemap index")
    issues: List[SitemapIssue] = Field(default_factory=list, description="Issues detected for this sitemap")
    recommendations: List[SitemapRecommendation] = Field(default_factory=list, description="Fix recommendations")
    urls: List[str] = Field(default_factory=list, description="URLs in this sitemap (for pagination)")
    raw_content: Optional[str] = Field(default=None, description="Raw XML content")
    content_length: int = Field(default=0, description="Content length in bytes")


class SitemapCheckData(BaseModel):
    """Main data payload."""
    url: str = Field(..., description="The URL that was checked")
    sitemaps: List[SitemapEntry] = Field(default_factory=list, description="Discovered sitemap files")


class SitemapCheckResponse(BaseModel):
    """Top-level API response."""
    data: SitemapCheckData
    cost: float = Field(default=0.0, description="API cost in seconds")


class SitemapCheckAcceptedResponse(BaseModel):
    """Response for the check endpoint with check_id for pagination."""
    check_id: str
    data: SitemapCheckData
    cost: float = Field(default=0.0)


# Pagination schemas (for /files, /files/{idx}/urls, /files/{idx}/raw)
class SitemapFilePageItem(BaseModel):
    index: int
    url: str
    status: int
    contentType: str
    entries: int
    isIndex: bool
    issues: List[SitemapIssue] = Field(default_factory=list)


class SitemapFilePage(BaseModel):
    items: List[SitemapFilePageItem]
    page: int
    page_size: int
    total: int
    has_next: bool


class SitemapUrlPage(BaseModel):
    sitemap_url: str
    items: List[str]
    page: int
    page_size: int
    total: int
    has_next: bool


class SitemapRawResponse(BaseModel):
    sitemap_url: str
    content_type: Optional[str] = None
    content_length: int = 0
    raw_content: Optional[str] = None
