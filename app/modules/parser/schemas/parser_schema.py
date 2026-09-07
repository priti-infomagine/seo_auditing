"""
Schemas for parser API endpoints.
"""
from pydantic import BaseModel, Field, field_validator
from typing import Optional, Dict, Any, List
from datetime import datetime


class ParseRequest(BaseModel):
    """Request schema for parsing a crawled website."""
    
    website: str = Field(
        ...,
        description="Website name or domain to parse (e.g., 'www.reddit.com' or 'https://www.reddit.com')",
        examples=["cyfuture.com", "https://cyfuture.com"]
    )
    
    @field_validator("website")
    @classmethod
    def validate_website(cls, v: str) -> str:
        """Validate and normalize website input."""
        website = v.strip().lower()
        
        # Remove protocol if present
        if website.startswith(("http://", "https://")):
            from urllib.parse import urlparse
            website = urlparse(website).netloc or website
        
        # Remove trailing slash
        website = website.rstrip("/")
        
        if not website or "." not in website:
            raise ValueError("Invalid website name. Provide a valid domain like 'example.com'")
        
        return website


class ParseResponse(BaseModel):
    """Response schema for parse request."""
    
    success: bool = Field(..., description="Whether parsing was successful")
    message: str = Field(..., description="Status message")
    website: str = Field(..., description="Website/domain that was parsed")
    test_number: int = Field(..., description="Test number for this domain")
    file_path: str = Field(..., description="Path to saved parsed data")
    parsed_at: str = Field(..., description="Timestamp of parsing")
    source_crawl_file: str = Field(..., description="Source crawl file used for parsing")
    data: Optional[Dict[str, Any]] = Field(None, description="Parsed data summary")


class ParseError(BaseModel):
    """Error response schema."""
    
    success: bool = False
    error: str = Field(..., description="Error type")
    detail: str = Field(..., description="Error details")