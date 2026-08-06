"""
Metadata extractor - extracts response and page metadata.
Returns structured metadata only, no persistence logic.
"""
from typing import Optional
from datetime import datetime


class ExtractedMetadata:
    """Structured metadata data."""
    def __init__(
        self,
        status_code: Optional[int] = None,
        content_type: Optional[str] = None,
        content_size: Optional[int] = None,
        response_time_ms: Optional[int] = None,
        final_url: Optional[str] = None,
    ):
        self.status_code = status_code
        self.content_type = content_type
        self.content_size = content_size
        self.response_time_ms = response_time_ms
        self.final_url = final_url


def extract_metadata(
    status_code: int,
    headers: dict,
    content: bytes,
    response_time_ms: int,
    final_url: Optional[str] = None,
) -> ExtractedMetadata:
    """
    Extract metadata from HTTP response.
    
    Args:
        status_code: HTTP status code
        headers: Response headers
        content: Response content bytes
        response_time_ms: Response time in milliseconds
        final_url: Final URL after redirects
        
    Returns:
        ExtractedMetadata object
    """
    content_type = headers.get("content-type", None)
    if content_type:
        content_type = content_type.split(";")[0].strip().lower()
    
    return ExtractedMetadata(
        status_code=status_code,
        content_type=content_type,
        content_size=len(content),
        response_time_ms=response_time_ms,
        final_url=final_url,
    )