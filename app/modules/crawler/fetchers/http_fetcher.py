"""
HttpFetcher - High performance httpx fetcher implementing Fetcher protocol.

Uses a single reusable httpx.AsyncClient per instance for connection pooling.
"""
import asyncio
import random
import time
from typing import Dict, Optional

import httpx

from app.modules.crawler.config import CrawlConfig
from app.modules.crawler.fetchers.base import Fetcher
from app.modules.crawler.types import FetchResult, RedirectInfo
from app.modules.crawler.utils.url import validate_url_ssrf
from app.shared.utils.url_utils import normalize_url as shared_normalize_url


class HttpFetcher(Fetcher):
    """Fetcher implementation using httpx.AsyncClient with connection pooling."""

    def __init__(self, config: Optional[CrawlConfig] = None):
        self.config = config or CrawlConfig()
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(self.config.request_timeout),
            follow_redirects=True,
            max_redirects=self.config.max_redirects,
            headers={
                "User-Agent": self.config.user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": self.config.accept_language,
            },
        )

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    async def __aenter__(self) -> "HttpFetcher":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()

    async def fetch(
        self,
        url: str,
        *,
        timeout: Optional[float] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> FetchResult:
        req_timeout = timeout if timeout is not None else self.config.request_timeout

        # SSRF Protection Check
        try:
            validate_url_ssrf(url, allow_private=self.config.allow_private_ips)
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
                error_type="ssrf_blocked",
                render_mode="http",
            )

        req_headers = dict(self._client.headers)
        if headers:
            req_headers.update(headers)

        start_time = time.perf_counter()
        max_retries = 3
        last_error = None
        last_error_type = None

        for attempt in range(1, max_retries + 1):
            try:
                response = await self._client.get(
                    url,
                    timeout=req_timeout,
                    headers=req_headers,
                )

                response_time_ms = int((time.perf_counter() - start_time) * 1000)
                norm_headers = {k.lower(): v for k, v in response.headers.items()}
                content = response.content

                # Content-size limit check
                if len(content) > self.config.max_response_size:
                    return FetchResult(
                        url=url,
                        normalized_url=shared_normalize_url(str(response.url)),
                        status_code=response.status_code,
                        content=b"",
                        headers=norm_headers,
                        final_url=str(response.url),
                        content_type=norm_headers.get("content-type"),
                        content_length=len(content),
                        response_time_ms=response_time_ms,
                        redirect_chain=[],
                        success=False,
                        error=f"Response size {len(content)} exceeds limit {self.config.max_response_size}",
                        error_type="content_too_large",
                        render_mode="http",
                    )

                redirects = []
                for r in response.history:
                    redirects.append(
                        RedirectInfo(
                            url=str(r.url),
                            status_code=r.status_code,
                            location=r.headers.get("location"),
                        )
                    )

                status_code = response.status_code

                # Transient retries (500, 502, 503, 504, 429)
                if status_code in (429, 500, 502, 503, 504) and attempt < max_retries:
                    await asyncio.sleep(0.5 * (2 ** (attempt - 1)) + random.uniform(0, 0.2))
                    continue

                return FetchResult(
                    url=url,
                    normalized_url=shared_normalize_url(str(response.url)),
                    status_code=status_code,
                    content=content,
                    headers=norm_headers,
                    final_url=str(response.url),
                    content_type=norm_headers.get("content-type"),
                    content_length=len(content),
                    response_time_ms=response_time_ms,
                    redirect_chain=redirects,
                    success=200 <= status_code < 400,
                    error=None,
                    error_type=None,
                    render_mode="http",
                )

            except (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError) as exc:
                last_error = str(exc)
                last_error_type = "timeout" if isinstance(exc, httpx.TimeoutException) else "network_error"
                if attempt < max_retries:
                    await asyncio.sleep(0.5 * (2 ** (attempt - 1)) + random.uniform(0, 0.2))
                    continue
                break
            except Exception as exc:
                last_error = str(exc)
                last_error_type = "fetch_error"
                break

        response_time_ms = int((time.perf_counter() - start_time) * 1000)
        return FetchResult(
            url=url,
            normalized_url=shared_normalize_url(url),
            status_code=0,
            content=b"",
            headers={},
            final_url=url,
            content_type=None,
            content_length=0,
            response_time_ms=response_time_ms,
            redirect_chain=[],
            success=False,
            error=last_error or "Fetch failed",
            error_type=last_error_type or "fetch_error",
            render_mode="http",
        )
