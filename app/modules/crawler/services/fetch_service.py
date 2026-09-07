"""
Crawler fetch service.

Responsibilities:
- Normalize and validate URLs
- Fetch pages through the shared HTTP client
- Handle transient HTTP failures with retry/backoff
- Respect Retry-After when available
- Capture response metadata
- Capture redirect chain
- Measure response time
- Classify transport errors

This module does NOT:
- Parse HTML
- Extract SEO data
- Evaluate SEO rules
- Persist data
"""

import asyncio
import random
import time
from dataclasses import dataclass
from typing import Optional

import httpx
from app.shared.utils.http_client import HTTPClient
from app.shared.utils.url_utils import normalize_url

from ..constants import (
    CRAWLABLE_SCHEMES,
    DEFAULT_MAX_REDIRECTS,
    DEFAULT_TIMEOUT,
    DEFAULT_USER_AGENT,
    HTTP_RETRY_STATUS_CODES,
)


DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF_BASE = 1.0
DEFAULT_BACKOFF_MAX = 30.0


@dataclass(slots=True)
class RedirectInfo:
    """Information about a single redirect."""

    url: str
    status_code: int
    location: Optional[str]


@dataclass(slots=True)
class FetchResult:
    """Structured result returned by the crawler fetch layer."""

    url: str
    normalized_url: str
    status_code: int

    content: bytes
    headers: dict[str, str]

    final_url: str
    content_type: Optional[str]
    content_length: int

    response_time_ms: int

    redirect_chain: list[RedirectInfo]

    success: bool

    error: Optional[str] = None
    error_type: Optional[str] = None


def _get_content_type(headers: dict[str, str]) -> Optional[str]:
    """
    Extract and normalize Content-Type.

    Example:
        text/html; charset=UTF-8
        -> text/html
    """
    content_type = headers.get("content-type")

    if not content_type:
        return None

    return content_type.split(";", 1)[0].strip().lower()


def _get_retry_after(
    headers: dict[str, str],
) -> Optional[float]:
    """
    Parse Retry-After header.

    Currently supports the integer-seconds form.

    Example:
        Retry-After: 5
        -> 5.0
    """
    value = headers.get("retry-after")

    if not value:
        return None

    try:
        seconds = float(value)

        if seconds < 0:
            return None

        return seconds

    except (TypeError, ValueError):
        return None


def _calculate_backoff(attempt: int) -> float:
    """
    Calculate exponential backoff with jitter.

    attempt=1 -> around 1s
    attempt=2 -> around 2s
    attempt=3 -> around 4s
    """
    exponential_delay = DEFAULT_BACKOFF_BASE * (2 ** (attempt - 1))

    delay = min(
        exponential_delay,
        DEFAULT_BACKOFF_MAX,
    )

    jitter = random.uniform(0, delay * 0.25)

    return delay + jitter


def _is_retryable_exception(error: httpx.HTTPError) -> bool:
    """Determine whether an HTTPX error is likely transient."""

    return isinstance(
        error,
        (
            httpx.TimeoutException,
            httpx.ConnectError,
            httpx.NetworkError,
            httpx.RemoteProtocolError,
        ),
    )


def _get_error_type(error: Exception) -> str:
    """Convert an exception into a stable crawler error category."""

    if isinstance(error, httpx.TimeoutException):
        return "timeout"

    if isinstance(error, httpx.ConnectError):
        return "connection_error"

    if isinstance(error, httpx.NetworkError):
        return "network_error"

    if isinstance(error, httpx.RemoteProtocolError):
        return "protocol_error"

    if isinstance(error, httpx.TooManyRedirects):
        return "too_many_redirects"

    if isinstance(error, httpx.UnsupportedProtocol):
        return "unsupported_protocol"

    if isinstance(error, httpx.InvalidURL):
        return "invalid_url"

    if isinstance(error, httpx.HTTPError):
        return "http_error"

    return "unknown_error"


def _build_redirect_chain(
    response: httpx.Response,
) -> list[RedirectInfo]:
    """
    Extract redirect history from HTTPX response.

    HTTPX stores previous responses in response.history.
    """

    redirects: list[RedirectInfo] = []

    for redirect_response in response.history:
        location = redirect_response.headers.get("location")

        redirects.append(
            RedirectInfo(
                url=str(redirect_response.url),
                status_code=redirect_response.status_code,
                location=location,
            )
        )

    return redirects


def _is_crawlable_scheme(url: str) -> bool:
    """Check whether the URL uses a crawlable HTTP scheme."""

    try:
        scheme = url.split(":", 1)[0].lower()

        return scheme in CRAWLABLE_SCHEMES

    except (AttributeError, ValueError):
        return False


async def fetch_page(
    url: str,
    timeout: float = DEFAULT_TIMEOUT,
    follow_redirects: bool = True,
    user_agent: Optional[str] = DEFAULT_USER_AGENT,
    max_redirects: int = DEFAULT_MAX_REDIRECTS,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> FetchResult:
    """
    Fetch a single URL.

    This method is responsible only for HTTP-level crawling.

    It does not parse HTML or perform SEO analysis.
    """

    try:
        normalized_url = normalize_url(url)
    except Exception as exc:
        return FetchResult(
            url=url,
            normalized_url=url,
            status_code=0,
            content=b"",
            headers={},
            final_url=url,
            content_type=None,
            content_length=0,
            response_time_ms=0,
            redirect_chain=[],
            success=False,
            error=str(exc),
            error_type="invalid_url",
        )

    if not _is_crawlable_scheme(normalized_url):
        return FetchResult(
            url=url,
            normalized_url=normalized_url,
            status_code=0,
            content=b"",
            headers={},
            final_url=normalized_url,
            content_type=None,
            content_length=0,
            response_time_ms=0,
            redirect_chain=[],
            success=False,
            error=f"Unsupported URL scheme: {normalized_url}",
            error_type="unsupported_scheme",
        )

    start_time = time.perf_counter()

    last_error: Optional[str] = None
    last_error_type: Optional[str] = None

    for attempt in range(1, max_retries + 1):

        try:
            async with HTTPClient(
                timeout=timeout,
                follow_redirects=follow_redirects,
                max_redirects=max_redirects,
                user_agent=user_agent,
            ) as client:
                response = await client.get(normalized_url)

            response_time_ms = int(
                (time.perf_counter() - start_time) * 1000
            )

            headers = {
                key.lower(): value
                for key, value in response.headers.items()
            }

            status_code = response.status_code

            # Retry transient HTTP responses.
            if (
                status_code in HTTP_RETRY_STATUS_CODES
                and attempt < max_retries
            ):
                retry_after = _get_retry_after(headers)

                delay = (
                    retry_after
                    if retry_after is not None
                    else _calculate_backoff(attempt)
                )

                await asyncio.sleep(delay)

                continue

            content = response.content

            return FetchResult(
                url=url,
                normalized_url=normalized_url,
                status_code=status_code,
                content=content,
                headers=headers,
                final_url=str(response.url),
                content_type=_get_content_type(headers),
                content_length=len(content),
                response_time_ms=response_time_ms,
                redirect_chain=_build_redirect_chain(response),
                success=200 <= status_code < 400,
                error=None,
                error_type=None,
            )

        except httpx.HTTPError as exc:

            last_error = str(exc)
            last_error_type = _get_error_type(exc)

            # Retry only transient transport-level failures.
            if (
                _is_retryable_exception(exc)
                and attempt < max_retries
            ):
                delay = _calculate_backoff(attempt)

                await asyncio.sleep(delay)

                continue

            break

    response_time_ms = int(
        (time.perf_counter() - start_time) * 1000
    )

    return FetchResult(
        url=url,
        normalized_url=normalized_url,
        status_code=0,
        content=b"",
        headers={},
        final_url=normalized_url,
        content_type=None,
        content_length=0,
        response_time_ms=response_time_ms,
        redirect_chain=[],
        success=False,
        error=last_error,
        error_type=last_error_type,
    )





# """
# fetch service - handles HTTP requests only.
# Pure HTTP fetching, no parsing logic.
# """
# import time
# from typing import Optional

# import httpx

# from app.shared.utils.http_client import HTTPClient
# from app.shared.utils.url_utils import normalize_url
# from ..constants import (
#     DEFAULT_TIMEOUT,
#     DEFAULT_MAX_REDIRECTS,
#     DEFAULT_USER_AGENT,
# )


# class FetchResult:
#     """Structured fetch result."""
#     def __init__(
#         self,
#         url: str,
#         status_code: int,
#         content: bytes,
#         headers: dict,
#         final_url: str,
#         response_time_ms: int,
#         error: Optional[str] = None,
#         response: Optional[httpx.Response] = None,
#     ):
#         self.url = url
#         self.status_code = status_code
#         self.content = content
#         self.headers = headers
#         self.final_url = final_url
#         self.response_time_ms = response_time_ms
#         self.error = error
#         # Raw httpx.Response (for redirect history, SSL info, etc.)
#         self._response = response


# async def fetch_page(
#     url: str,
#     timeout: int = DEFAULT_TIMEOUT,
#     follow_redirects: bool = True,
#     max_redirects: int = DEFAULT_MAX_REDIRECTS,
#     user_agent: Optional[str] = DEFAULT_USER_AGENT,
# ) -> FetchResult:
#     """
#     Fetch a page and return structured result.

#     Args:
#         url: URL to fetch
#         timeout: Request timeout in seconds
#         follow_redirects: Whether to follow redirects
#         max_redirects: Maximum number of redirects to follow
#         user_agent: Optional user agent string

#     Returns:
#         FetchResult object
#     """
#     normalized = normalize_url(url)
#     start_time = time.perf_counter()

#     try:
#         response = await HTTPClient(
#             normalized,
#             timeout=timeout,
#             follow_redirects=follow_redirects,
#             max_redirects=max_redirects,
#             user_agent=user_agent,
#         )
#         response_time_ms = int((time.perf_counter() - start_time) * 1000)

#         return FetchResult(
#             url=normalized,
#             status_code=response.status_code,
#             content=response.content,
#             headers=dict(response.headers),
#             final_url=str(response.url),
#             response_time_ms=response_time_ms,
#             response=response,
#         )
#     except httpx.HTTPError as e:
#         response_time_ms = int((time.perf_counter() - start_time) * 1000)
#         return FetchResult(
#             url=normalized,
#             status_code=0,
#             content=b"",
#             headers={},
#             final_url=normalized,
#             response_time_ms=response_time_ms,
#             error=str(e),
#         )
