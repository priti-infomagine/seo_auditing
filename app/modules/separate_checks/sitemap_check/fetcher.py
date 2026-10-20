"""
Sitemap HTTP fetcher.

Fetches sitemap files (and robots.txt) with HTTPS-first → HTTP-fallback,
gzip decompression, redirect-following, and error classification that
reuses the crawler's ``fetch_service`` backoff helpers.

The robots.txt fetch delegates to ``robots_check.fetcher.fetch_robots_txt``
so the same retry/backoff/HTTPS-fallback logic is shared.
"""
import asyncio
import time
from dataclasses import dataclass
from typing import Optional

import httpx

from app.core.logger import logger
from app.modules.crawler.constants import DEFAULT_TIMEOUT, DEFAULT_USER_AGENT
from app.shared.utils.http_client import HTTPClient

from .model import FetchStatus

DEFAULT_MAX_RETRIES = 3


@dataclass(slots=True)
class SitemapFetchResult:
    """Structured result returned by :func:`fetch_sitemap`."""

    url: str
    final_url: str
    status_code: Optional[int]
    content_type: str
    content: bytes
    content_length: int
    response_time_ms: int
    error: Optional[str] = None
    success: bool = False
    fetch_status: FetchStatus = FetchStatus.UNREACHABLE


async def fetch_sitemap(
    url: str,
    timeout: float = DEFAULT_TIMEOUT,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> SitemapFetchResult:
    """Fetch a single sitemap URL, following redirects and decompressing gzip.

    HTTPS-first → HTTP-fallback only applies when the *requested* URL uses
    ``https://`` and the connection itself fails (not a 4xx/5xx response);
    in that case an ``http://`` variant is tried.

    Returns a :class:`SitemapFetchResult`.  On connection failure the
    result has ``fetch_status=UNREACHABLE``; on 404 ``NOT_FOUND``;
    on 200 ``SUCCESS``.
    """
    start = time.perf_counter()
    result = await _try_fetch(url, timeout, max_retries)
    result.response_time_ms = int((time.perf_counter() - start) * 1000)

    if (
        not result.success
        and result.fetch_status == FetchStatus.UNREACHABLE
        and url.startswith("https://")
    ):
        http_url = url.replace("https://", "http://", 1)
        logger.info(
            "fetch_sitemap: HTTPS failed for %s (%s) — trying HTTP fallback",
            url,
            result.error,
        )
        http_result = await _try_fetch(http_url, timeout, max_retries)
        http_result.response_time_ms = int(
            (time.perf_counter() - start) * 1000
        )
        return http_result

    return result


async def _try_fetch(
    url: str,
    timeout: float,
    max_retries: int,
) -> SitemapFetchResult:
    """Single-attempt fetch with retry loop and error classification."""
    from app.modules.crawler.services.fetch_service import (
        _calculate_backoff,
        _is_retryable_exception,
    )

    last_error: Optional[str] = None

    for attempt in range(1, max_retries + 1):
        try:
            async with HTTPClient(
                timeout=timeout,
                follow_redirects=True,
                user_agent=DEFAULT_USER_AGENT,
            ) as client:
                response = await client.get(url)

            content = response.content
            final_url = str(response.url)
            content_type = (
                response.headers.get("content-type", "")
                if response.headers
                else ""
            )

            from .parser import decompress_sitemap_content

            content, _was_gzipped = decompress_sitemap_content(
                content, content_type, url
            )

            if response.status_code == 404:
                return SitemapFetchResult(
                    url=url,
                    final_url=final_url,
                    status_code=404,
                    content_type=content_type.split(";")[0].strip().lower(),
                    content=b"",
                    content_length=0,
                    response_time_ms=0,
                    success=False,
                    fetch_status=FetchStatus.NOT_FOUND,
                )

            if 200 <= response.status_code < 400:
                return SitemapFetchResult(
                    url=url,
                    final_url=final_url,
                    status_code=response.status_code,
                    content_type=content_type.split(";")[0].strip().lower(),
                    content=content,
                    content_length=len(content),
                    response_time_ms=0,
                    success=True,
                    fetch_status=FetchStatus.SUCCESS,
                )

            last_error = f"HTTP {response.status_code}"

            if response.status_code in {429, 500, 502, 503, 504, 408}:
                if attempt < max_retries:
                    delay = _calculate_backoff(attempt)
                    await asyncio.sleep(delay)
                    continue

        except httpx.HTTPError as exc:
            last_error = str(exc)
            if (
                _is_retryable_exception(exc)
                and attempt < max_retries
            ):
                delay = _calculate_backoff(attempt)
                await asyncio.sleep(delay)
                continue
            break

        except Exception as exc:
            last_error = str(exc)
            if attempt < max_retries:
                delay = _calculate_backoff(attempt)
                await asyncio.sleep(delay)
                continue
            break

    return SitemapFetchResult(
        url=url,
        final_url=url,
        status_code=0,
        content_type="",
        content=b"",
        content_length=0,
        response_time_ms=0,
        error=f"unreachable: {last_error}" if last_error else None,
        success=False,
        fetch_status=FetchStatus.UNREACHABLE,
    )
