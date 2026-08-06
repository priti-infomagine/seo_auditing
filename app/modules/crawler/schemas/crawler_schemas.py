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
    
    success: bool = Field(..., description="Whether crawl was successful")
    message: str = Field(..., description="Status message")
    url: str = Field(..., description="Crawled URL")
    domain: str = Field(..., description="Domain name")
    test_number: int = Field(..., description="Test number for this domain")
    file_path: str = Field(..., description="Path to saved crawl data")
    crawled_at: str = Field(..., description="Timestamp of crawl")
    data: Optional[Dict[str, Any]] = Field(None, description="Crawled data summary")


class CrawlError(BaseModel):
    """Error response schema."""
    
    success: bool = False
    error: str = Field(..., description="Error type")
    detail: str = Field(..., description="Error details")