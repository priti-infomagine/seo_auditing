"""
Fetch service - handles HTTP requests only.
Pure HTTP fetching, no parsing logic.
"""
import time
from typing import Optional

import httpx

from app.shared.utils.http_client import fetch_url
from app.shared.utils.url_utils import normalize_url


class FetchResult:
    """Structured fetch result."""
    def __init__(
        self,
        url: str,
        status_code: int,
        content: bytes,
        headers: dict,
        final_url: str,
        response_time_ms: int,
        error: Optional[str] = None,
        response: Optional[httpx.Response] = None,
    ):
        self.url = url
        self.status_code = status_code
        self.content = content
        self.headers = headers
        self.final_url = final_url
        self.response_time_ms = response_time_ms
        self.error = error
        # Raw httpx.Response (for redirect history, SSL info, etc.)
        self._response = response


async def fetch_page(
    url: str,
    timeout: int = 30,
    follow_redirects: bool = True,
    user_agent: Optional[str] = None,
) -> FetchResult:
    """
    Fetch a page and return structured result.

    Args:
        url: URL to fetch
        timeout: Request timeout in seconds
        follow_redirects: Whether to follow redirects
        user_agent: Optional user agent string

    Returns:
        FetchResult object
    """
    normalized = normalize_url(url)
    start_time = time.time()

    try:
        response = await fetch_url(
            normalized,
            timeout=timeout,
            follow_redirects=follow_redirects,
            user_agent=user_agent,
        )
        response_time_ms = int((time.time() - start_time) * 1000)

        return FetchResult(
            url=normalized,
            status_code=response.status_code,
            content=response.content,
            headers=dict(response.headers),
            final_url=str(response.url),
            response_time_ms=response_time_ms,
            response=response,
        )
    except httpx.HTTPError as e:
        response_time_ms = int((time.time() - start_time) * 1000)
        return FetchResult(
            url=normalized,
            status_code=0,
            content=b"",
            headers={},
            final_url=normalized,
            response_time_ms=response_time_ms,
            error=str(e),
        )
