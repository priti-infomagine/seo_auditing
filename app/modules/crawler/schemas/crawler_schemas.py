"""
Schemas for crawler API endpoints.
"""
from app.core.config import settings
from pydantic import BaseModel, Field, HttpUrl, field_validator
from typing import Optional, Dict, Any, List
from datetime import datetime
from uuid import UUID


class CrawlRequest(BaseModel):
    """Request schema for crawling a URL."""
    
    url: HttpUrl = Field(
        ...,
        description="URL to crawl",
        examples=["https://example.com"]
    )
    
    max_depth: int = Field(5, description="Maximum crawl depth")
    max_pages: int = Field(default_factory=lambda: settings.CRAWL_MAX_PAGES, description="Maximum pages to crawl")
    concurrency: int = Field(10, description="Concurrent requests")
    auto_analyze: bool = Field(
        False,
        description="If true, automatically run parse → evaluate → score pipeline after crawl completes"
    )
    project_id: Optional[UUID] = Field(
        None,
        description="Project identifier for tracking. If None, a new UUID is generated.",
    )
    
    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        """Validate URL format and protocol."""
        url_str = str(v)
        
        # Ensure HTTP/HTTPS protocol
        if not url_str.startswith(("http://", "https://")):
            raise ValueError("URL must start with http:// or https://")
        
        return url_str


class CrawlResponse(BaseModel):
    """Response schema for crawl request."""

    crawl_id: str = Field(..., description="Unique crawl job identifier")
    status: str = Field(..., description="Current crawl job status")
    message: str = Field(..., description="Status message")
    project_id: str = Field(..., description="Project identifier for tracking the analysis pipeline")
    task_id: str = Field(..., description="Celery task ID for progress polling via result backend")


class CrawlStatusResponse(BaseModel):
    """Response schema for crawl status."""

    crawl_id: str = Field(..., description="Unique crawl job identifier")
    status: str = Field(..., description="Current crawl job status")
    domain: str = Field(..., description="Domain being crawled")
    url: str = Field(..., description="Crawled URL")
    error: str | None = Field(None, description="Error message if crawl failed")
    started_at: str | None = Field(None, description="When crawl started")
    completed_at: str | None = Field(None, description="When crawl completed")
    duration_ms: int | None = Field(None, description="Crawl duration in milliseconds")
    pages_crawled: int = Field(0, description="Number of pages crawled")
    pages_discovered: int | None = Field(None, description="Total pages discovered")
    pages_failed: int = Field(0, description="Number of failed pages")
    total_pages: int | None = Field(None, description="Total pages configured to crawl")
    current_page: int | None = Field(None, description="Current page being processed")
    progress_percent: int | None = Field(None, description="Crawl progress as a percentage (0-100)")
    total_errors: int = Field(0, description="Number of crawl errors")


class TestCrawlResponse(BaseModel):
    """Response schema for synchronous test crawl."""

    success: bool = Field(..., description="Whether the crawl completed successfully")
    crawl_id: str = Field(..., description="Unique crawl job identifier")
    status: str = Field(..., description="Final crawl job status")
    url: str = Field(..., description="Crawled URL")
    domain: str = Field(..., description="Domain being crawled")
    pages_crawled: int = Field(..., description="Number of pages crawled")
    total_errors: int = Field(..., description="Total number of crawl errors")
    duration_ms: int = Field(..., description="Crawl duration in milliseconds")
    started_at: str | None = Field(None, description="When crawl started (ISO 8601)")
    completed_at: str | None = Field(None, description="When crawl completed (ISO 8601)")
    pages: list[dict] = Field(default_factory=list, description="List of crawled pages with details")
    errors: list[dict] = Field(default_factory=list, description="List of crawl errors")
    crawl_config: dict = Field(default_factory=dict, description="Crawl configuration used")


class CrawlError(BaseModel):
    """Error response schema."""

    success: bool = False
    error: str = Field(..., description="Error type")
    detail: str = Field(..., description="Error details")