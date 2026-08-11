"""
Schemas for crawler API endpoints.
"""
from pydantic import BaseModel, Field, HttpUrl, field_validator
from typing import Optional, Dict, Any, List
from datetime import datetime


class CrawlRequest(BaseModel):
    """Request schema for crawling a URL."""
    
    url: HttpUrl = Field(
        ...,
        description="URL to crawl",
        examples=["https://example.com"]
    )
    
    max_depth: int = Field(5, description="Maximum crawl depth")
    max_pages: int = Field(1000, description="Maximum pages to crawl")
    concurrency: int = Field(10, description="Concurrent requests")
    
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