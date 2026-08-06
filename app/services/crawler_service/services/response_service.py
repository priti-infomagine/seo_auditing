"""
Response service - converts raw HTTP response into structured response object.
Pure transformation logic, no parsing.
"""
from typing import Optional

from app.services.crawler_service.extractors.metadata_extractor import (
    ExtractedMetadata,
    extract_metadata,
)


class ProcessedResponse:
    """Structured processed response."""
    def __init__(
        self,
        fetch_result,
        metadata: ExtractedMetadata,
        content: bytes,
    ):
        self.fetch_result = fetch_result
        self.metadata = metadata
        self.content = content


def process_response(
    fetch_result,
) -> Optional[ProcessedResponse]:
    """
    Process raw HTTP response into structured object.

    Args:
        fetch_result: FetchResult from fetch_service

    Returns:
        ProcessedResponse object or None if error
    """
    if fetch_result.error:
        return None

    # Extract metadata
    metadata = extract_metadata(
        status_code=fetch_result.status_code,
        headers=fetch_result.headers,
        content=fetch_result.content,
        response_time_ms=fetch_result.response_time_ms,
        final_url=fetch_result.final_url,
    )

    return ProcessedResponse(
        fetch_result=fetch_result,
        metadata=metadata,
        content=fetch_result.content,
    )
