"""
Robots.txt HTTP fetcher.

Fetches ``/robots.txt`` for a given domain with HTTPS-first → HTTP-fallback,
retry/backoff, and error classification that reuses the crawler's
``fetch_service`` helpers.
"""
import asyncio
import time
from dataclasses import dataclass, field
from typing import Optional

import httpx

from app.core.logger import logger
from app.modules.crawler.constants import DEFAULT_TIMEOUT, DEFAULT_USER_AGENT
from app.modules.crawler.services.fetch_service import (
    _calculate_backoff,
    _get_error_type,
    _is_retryable_exception,
)
from app.shared.utils.http_client import HTTPClient

from .validation import build_robots_url
from .model import FetchStatus

DEFAULT_MAX_RETRIES = 3


@dataclass(slots=True)
class FetchResult:
    """Structured result returned by :func:`fetch_robots_txt`."""

    url: str
    text: str
    status_code: Optional[int]
    response_time_ms: int
    final_url: str
    content_length: int
    error: Optional[str] = None
    success: bool = False
    fetch_status: FetchStatus = FetchStatus.UNREACHABLE


@dataclass(slots=True)
class Evaluation:
    """Structured evaluation result from the evaluator."""

    findings: list[dict] = field(default_factory=list)
    overall_status: str = "not_applicable"
    severity: str = "none"
    blocks_entire_site: bool = False
    blocks_assets: bool = False
    oversized: bool = False
    evidence_str: Optional[str] = None


@dataclass(slots=True)
class ParsedRobots:
    """Structured parse result from the parser."""

    user_agent_groups: list[dict] = field(default_factory=list)
    sitemaps: list[str] = field(default_factory=list)
    crawl_delay: Optional[int] = None
    syntax_warnings: list[str] = field(default_factory=list)
    raw_text: str = ""


async def fetch_robots_txt(
    domain: str,
    timeout: float = DEFAULT_TIMEOUT,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> FetchResult:
    """Fetch ``robots.txt`` for *domain*.

    Tries HTTPS first; if the HTTPS request fails with a *connection* error
    (not a 4xx/5xx HTTP response), falls back to HTTP.

    Retries transient transport failures using the same backoff strategy
    as :func:`fetch_service.fetch_page`.
    """
    https_url = build_robots_url(domain, scheme="https")
    http_url = build_robots_url(domain, scheme="http")

    start = time.perf_counter()

    fetch_result = await _try_fetch(
        https_url, timeout, max_retries, expect_404=True
    )

    if fetch_result.success:
        return _finalize(fetch_result, start)

    if fetch_result.fetch_status == FetchStatus.NOT_FOUND:
        return _finalize(fetch_result, start)

    if fetch_result.fetch_status == FetchStatus.UNREACHABLE:
        logger.info(
            "fetch_robots_txt: HTTPS failed for %s (%s) — trying HTTP fallback",
            domain,
            fetch_result.error,
        )
        http_result = await _try_fetch(
            http_url, timeout, max_retries, expect_404=True
        )
        if http_result.success or http_result.fetch_status == FetchStatus.NOT_FOUND:
            return _finalize(http_result, start)
        return _finalize(http_result, start)

    return _finalize(fetch_result, start)


async def _try_fetch(
    url: str,
    timeout: float,
    max_retries: int,
    expect_404: bool = True,
) -> FetchResult:
    """Single-attempt fetch with retry loop and error classification."""
    last_error: Optional[str] = None
    last_error_type: Optional[str] = None

    for attempt in range(1, max_retries + 1):
        try:
            async with HTTPClient(
                timeout=timeout,
                follow_redirects=True,
                user_agent=DEFAULT_USER_AGENT,
            ) as client:
                response = await client.get(url)

            text = response.text
            final_url = str(response.url)
            content_length = len(response.content)

            if response.status_code == 404:
                return FetchResult(
                    url=url,
                    text="",
                    status_code=404,
                    response_time_ms=0,
                    final_url=final_url,
                    content_length=0,
                    success=False,
                    fetch_status=FetchStatus.NOT_FOUND,
                )

            if 200 <= response.status_code < 400:
                return FetchResult(
                    url=url,
                    text=text,
                    status_code=response.status_code,
                    response_time_ms=0,
                    final_url=final_url,
                    content_length=content_length,
                    success=True,
                    fetch_status=FetchStatus.SUCCESS,
                )

            last_error = f"HTTP {response.status_code}"
            last_error_type = "http_error"

            if response.status_code in {429, 500, 502, 503, 504, 408}:
                if attempt < max_retries:
                    delay = _calculate_backoff(attempt)
                    await asyncio.sleep(delay)
                    continue

        except httpx.HTTPStatusError as exc:
            last_error = str(exc)
            last_error_type = _get_error_type(exc)
            if _is_retryable_exception(exc) and attempt < max_retries:
                delay = _calculate_backoff(attempt)
                await asyncio.sleep(delay)
                continue
            break

        except httpx.HTTPError as exc:
            last_error = str(exc)
            last_error_type = _get_error_type(exc)

            if _is_retryable_exception(exc) and attempt < max_retries:
                delay = _calculate_backoff(attempt)
                await asyncio.sleep(delay)
                continue
            break

        except Exception as exc:
            last_error = str(exc)
            last_error_type = "unknown_error"
            if attempt < max_retries:
                delay = _calculate_backoff(attempt)
                await asyncio.sleep(delay)
                continue
            break

    return FetchResult(
        url=url,
        text="",
        status_code=0,
        response_time_ms=0,
        final_url=url,
        content_length=0,
        error=f"{last_error_type}: {last_error}" if last_error else None,
        success=False,
        fetch_status=FetchStatus.UNREACHABLE,
    )


def _finalize(
    result: FetchResult, start: float
) -> FetchResult:
    result.response_time_ms = int((time.perf_counter() - start) * 1000)
    return result
