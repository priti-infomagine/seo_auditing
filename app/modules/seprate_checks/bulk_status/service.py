"""Bounded HTTPX and pooled Chromium redirect checks."""
from __future__ import annotations

import asyncio
import random
import re
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Optional
from urllib.parse import urljoin, urlsplit

import httpx

from app.core.config import settings
from app.core.logger import logger
from app.modules.crawler.config import CrawlConfig
from app.modules.crawler.rendering.browser_pool import BrowserPool
from app.modules.crawler.utils.url import validate_url_ssrf
from app.shared.utils.url_utils import get_domain

from .schema import (
    USER_AGENTS,
    RedirectCheckRequest,
    RedirectData,
    RedirectHeader,
    RedirectHop,
    RedirectResponse,
    RedirectResult,
    UserAgentInfo,
)


_REDIRECT_STATUSES = {301, 302, 303, 307, 308}
_RETRY_STATUSES = {408, 425, 429, 500, 502, 503, 504}
_SENSITIVE_HEADERS = {"authorization", "proxy-authorization", "set-cookie", "cookie"}
_FALLBACK_PATTERN = re.compile(
    r"<meta[^>]+http-equiv\s*=\s*['\"]?refresh|"
    r"(?:window\s*\.\s*)?location\s*=|"
    r"(?:window\s*\.\s*)?location\s*\.\s*(?:href|replace|assign)\s*=|"
    r"(?:window\s*\.\s*)?location\s*\.\s*(?:replace|assign)\s*\(",
    re.IGNORECASE,
)
_MAX_HTML_SNIFF_BYTES = 1_000_000
_MAX_RETRIES = 2


class RedirectCheckInfrastructureError(RuntimeError):
    """Raised when domain discovery cannot produce any checkable page."""


def _response_headers(headers) -> list[RedirectHeader]:
    return [
        RedirectHeader(name=name.lower(), value=value, ok=True)
        for name, value in headers.items()
        if name.lower() not in _SENSITIVE_HEADERS
    ]


def _retry_after(response: httpx.Response) -> Optional[float]:
    value = response.headers.get("retry-after")
    if not value:
        return None
    try:
        return min(max(float(value), 0.0), 2.0)
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(value)
            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=timezone.utc)
            return min(max((retry_at - datetime.now(timezone.utc)).total_seconds(), 0.0), 2.0)
        except (TypeError, ValueError, OverflowError):
            return None


class RedirectCheckerService:
    """Process URL and domain checks without persisting result data."""

    def __init__(
        self,
        *,
        http_transport: Optional[httpx.AsyncBaseTransport] = None,
        browser_pool: Optional[BrowserPool] = None,
        site_crawler_factory=None,
    ) -> None:
        self.http_transport = http_transport
        self.browser_pool = browser_pool
        self.site_crawler_factory = site_crawler_factory

    async def check(self, request: RedirectCheckRequest) -> RedirectResponse:
        started = time.perf_counter()
        user_agent_label, user_agent_string = USER_AGENTS[request.user_agent]
        if request.mode == "urls":
            results = await self._check_urls(request.urls or [], user_agent_string)
            truncated = 0
        else:
            urls, truncated = await self._discover_domain_urls(
                request.domain or "", request.max_urls
            )
            results = await self._check_browser_urls(urls, user_agent_string)

        return RedirectResponse(
            data=RedirectData(
                results=results,
                checked=len(results),
                truncated=truncated,
                maxUrls=request.max_urls,
                userAgent=UserAgentInfo(key=request.user_agent, label=user_agent_label),
            ),
            cost=round(time.perf_counter() - started, 3),
        )

    async def _check_urls(self, urls: list[str], user_agent: str) -> list[RedirectResult]:
        concurrency = max(1, settings.LINK_CHECK_MAX_CONCURRENCY)
        timeout = httpx.Timeout(
            timeout=settings.LINK_CHECK_TIMEOUT,
            connect=min(settings.LINK_CHECK_TIMEOUT, 5.0),
            pool=min(settings.LINK_CHECK_TIMEOUT, 5.0),
        )
        limits = httpx.Limits(
            max_connections=concurrency,
            max_keepalive_connections=concurrency,
        )
        async with httpx.AsyncClient(
            transport=self.http_transport,
            timeout=timeout,
            limits=limits,
            follow_redirects=False,
            headers={"User-Agent": user_agent},
        ) as client:
            semaphore = asyncio.Semaphore(concurrency)

            async def check_one(url: str) -> RedirectResult:
                async with semaphore:
                    result, html = await self._check_http_url(url, client)
                    if (
                        result.final_status is not None
                        and 200 <= result.final_status < 300
                        and html
                        and _FALLBACK_PATTERN.search(html)
                    ):
                        logger.info("Redirect checker using browser fallback for %s", url)
                        return await self._check_browser_url(url, user_agent)
                    return result

            return list(await asyncio.gather(*(check_one(url) for url in urls)))

    async def _check_http_url(
        self, url: str, client: httpx.AsyncClient
    ) -> tuple[RedirectResult, str]:
        hops: list[RedirectHop] = []
        current_url = url
        seen = {current_url}
        html = ""
        max_redirects = max(0, settings.LINK_ANALYSIS_MAX_REDIRECT_HOPS)

        while True:
            try:
                await asyncio.to_thread(validate_url_ssrf, current_url, False)
            except Exception:
                return self._failed_result(url, hops, current_url, "Unsafe or invalid redirect destination."), html

            response = None
            latency_ms = 0
            try:
                for attempt in range(_MAX_RETRIES + 1):
                    request_started = time.perf_counter()
                    try:
                        request = client.build_request("GET", current_url)
                        response = await client.send(request, stream=True)
                    except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError) as exc:
                        if attempt < _MAX_RETRIES:
                            await asyncio.sleep(0.15 * (2 ** attempt) + random.uniform(0, 0.1))
                            continue
                        category = "Request timed out." if isinstance(exc, httpx.TimeoutException) else "Connection failed."
                        logger.warning("Redirect HTTP failure for %s (%s)", current_url, type(exc).__name__)
                        return self._failed_result(url, hops, current_url, category), html
                    except httpx.InvalidURL:
                        return self._failed_result(url, hops, current_url, "Invalid URL."), html
                    except httpx.HTTPError as exc:
                        logger.warning(
                            "Redirect HTTP transport failure for %s (%s)",
                            current_url,
                            type(exc).__name__,
                        )
                        return self._failed_result(url, hops, current_url, "Connection failed."), html
                    latency_ms = int((time.perf_counter() - request_started) * 1000)
                    if response.status_code in _RETRY_STATUSES and attempt < _MAX_RETRIES:
                        delay = _retry_after(response)
                        if delay is None:
                            delay = 0.15 * (2 ** attempt) + random.uniform(0, 0.1)
                        await response.aclose()
                        await asyncio.sleep(delay)
                        continue
                    break

                if response is None:
                    return self._failed_result(url, hops, current_url, "Request failed."), html

                location = response.headers.get("location")
                resolved = urljoin(current_url, location) if location else None
                is_redirect = response.status_code in _REDIRECT_STATUSES
                hop = RedirectHop(
                    url=current_url,
                    status=response.status_code,
                    statusText=response.reason_phrase or "",
                    location=location,
                    resolved=resolved if is_redirect else None,
                    latencyMs=latency_ms,
                    headers=_response_headers(response.headers),
                )
                hops.append(hop)

                if is_redirect and location:
                    if len(hops) - 1 >= max_redirects:
                        return RedirectResult(
                            input=url,
                            hops=hops,
                            redirects=sum(h.status in _REDIRECT_STATUSES for h in hops),
                            finalUrl=resolved,
                            finalStatus=None,
                            error="Maximum redirect limit exceeded.",
                        ), html
                    parsed_destination = urlsplit(resolved or "")
                    if (
                        not resolved
                        or parsed_destination.scheme.lower() not in {"http", "https"}
                        or parsed_destination.username is not None
                        or parsed_destination.password is not None
                    ):
                        return self._failed_result(url, hops, current_url, "Redirect destination is unsafe or uses an unsupported scheme."), html
                    if resolved in seen:
                        return RedirectResult(
                            input=url,
                            hops=hops,
                            redirects=sum(h.status in _REDIRECT_STATUSES for h in hops),
                            finalUrl=resolved,
                            finalStatus=response.status_code,
                            error="Redirect loop detected.",
                        ), html
                    seen.add(resolved)
                    current_url = resolved
                    continue

                if is_redirect and not location:
                    return RedirectResult(
                        input=url,
                        hops=hops,
                        redirects=sum(h.status in _REDIRECT_STATUSES for h in hops),
                        finalUrl=current_url,
                        finalStatus=response.status_code,
                        error="Redirect response did not include a Location header.",
                    ), html

                content_type = response.headers.get("content-type", "").lower()
                if "text/html" in content_type or "application/xhtml+xml" in content_type:
                    try:
                        sniffed = bytearray()
                        async for chunk in response.aiter_bytes():
                            remaining = _MAX_HTML_SNIFF_BYTES - len(sniffed)
                            sniffed.extend(chunk[:remaining])
                            if len(sniffed) >= _MAX_HTML_SNIFF_BYTES:
                                break
                        html = bytes(sniffed).decode(response.encoding or "utf-8", errors="replace")
                    except (httpx.HTTPError, UnicodeError):
                        html = ""
                return RedirectResult(
                    input=url,
                    hops=hops,
                    redirects=sum(h.status in _REDIRECT_STATUSES for h in hops),
                    finalUrl=current_url,
                    finalStatus=response.status_code,
                    error=None,
                ), html
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error(
                    "Unexpected redirect check failure for %s (%s)",
                    current_url,
                    type(exc).__name__,
                    exc_info=True,
                )
                return self._failed_result(url, hops, current_url, "Redirect check failed."), html
            finally:
                if response is not None and not response.is_closed:
                    await response.aclose()

    async def _discover_domain_urls(self, domain: str, max_urls: int) -> tuple[list[str], int]:
        if self.site_crawler_factory is None:
            from app.modules.seprate_checks.link_analysis.crawler import SiteCrawler

            crawler_factory = SiteCrawler
        else:
            crawler_factory = self.site_crawler_factory

        crawler = crawler_factory(
            canonical_url=domain,
            domain=get_domain(domain),
            max_pages=max_urls,
        )
        crawl_result = await crawler.crawl()
        urls = list(crawl_result.graph.pages)
        urls = list(dict.fromkeys(urls))[:max_urls]
        if not urls and crawl_result.pages_crawled == 0:
            raise RedirectCheckInfrastructureError(
                "Domain URL discovery did not process any pages."
            )
        truncated = int(bool(crawl_result.crawl_truncated))
        return urls, truncated

    async def _check_browser_urls(self, urls: list[str], user_agent: str) -> list[RedirectResult]:
        concurrency = max(1, settings.LINK_CHECK_MAX_CONCURRENCY)
        semaphore = asyncio.Semaphore(concurrency)

        async def check_one(url: str) -> RedirectResult:
            async with semaphore:
                return await self._check_browser_url(url, user_agent)

        return list(await asyncio.gather(*(check_one(url) for url in urls)))

    async def _check_browser_url(self, url: str, user_agent: str) -> RedirectResult:
        config = CrawlConfig(
            user_agent=user_agent,
            browser_timeout=max(1, int(settings.LINK_ANALYSIS_PAGE_TIMEOUT)),
            request_timeout=settings.LINK_CHECK_TIMEOUT,
            enable_browser_rendering=False,
        )
        pool = self.browser_pool or BrowserPool.get_instance(config)
        responses = []
        request_starts = {}
        blocked_destinations = []
        navigation_started = time.perf_counter()

        try:
            async with pool.get_page(config) as page:
                if page is None:
                    return self._failed_result(url, [], url, "Browser is unavailable.")

                def on_request(request):
                    try:
                        if request.is_navigation_request() and request.frame == page.main_frame:
                            request_starts[id(request)] = time.perf_counter()
                    except Exception:
                        return

                def on_response(response):
                    try:
                        request = response.request
                        if request.is_navigation_request() and request.frame == page.main_frame:
                            responses.append((
                                response,
                                request_starts.get(id(request), navigation_started),
                                time.perf_counter(),
                            ))
                    except Exception:
                        return

                async def guard_route(route):
                    request_url = route.request.url
                    scheme = urlsplit(request_url).scheme.lower()
                    try:
                        is_main_navigation = (
                            route.request.is_navigation_request()
                            and route.request.frame == page.main_frame
                        )
                    except Exception:
                        is_main_navigation = False
                    if scheme not in {"http", "https"}:
                        if scheme in {"about", "data", "blob"} and not is_main_navigation:
                            await route.continue_()
                        else:
                            if is_main_navigation:
                                blocked_destinations.append(request_url)
                            await route.abort("blockedbyclient")
                        return
                    parsed_request = urlsplit(request_url)
                    if parsed_request.username is not None or parsed_request.password is not None:
                        if is_main_navigation:
                            blocked_destinations.append(request_url)
                        await route.abort("blockedbyclient")
                        return
                    try:
                        await asyncio.to_thread(validate_url_ssrf, request_url, False)
                    except Exception:
                        if is_main_navigation:
                            blocked_destinations.append(request_url)
                        await route.abort("blockedbyclient")
                        return
                    await route.continue_()

                page.on("request", on_request)
                page.on("response", on_response)
                await page.route("**/*", guard_route)
                await page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=config.browser_timeout * 1000,
                )
                try:
                    await page.wait_for_load_state("networkidle", timeout=2000)
                except Exception as exc:
                    logger.debug(
                        "Redirect browser did not reach network idle for %s (%s)",
                        url,
                        type(exc).__name__,
                    )

                hops = []
                for response, request_started, response_received in responses:
                    headers = await response.all_headers()
                    location = headers.get("location")
                    response_url = response.url
                    hops.append(RedirectHop(
                        url=response_url,
                        status=response.status,
                        statusText=response.status_text or "",
                        location=location,
                        resolved=(
                            urljoin(response_url, location)
                            if location and response.status in _REDIRECT_STATUSES
                            else None
                        ),
                        latencyMs=int((response_received - request_started) * 1000),
                        headers=_response_headers(headers),
                    ))

                final_status = hops[-1].status if hops else None
                return RedirectResult(
                    input=url,
                    hops=hops,
                    redirects=sum(h.status in _REDIRECT_STATUSES for h in hops),
                    finalUrl=page.url,
                    finalStatus=final_status,
                    error="Unsafe navigation destination was blocked." if blocked_destinations else None,
                )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(
                "Redirect browser check failed for %s (%s)", url, type(exc).__name__
            )
            partial_hops = []
            for response, request_started, response_received in responses:
                try:
                    headers = await response.all_headers()
                    location = headers.get("location")
                    response_url = response.url
                    partial_hops.append(RedirectHop(
                        url=response_url,
                        status=response.status,
                        statusText=response.status_text or "",
                        location=location,
                        resolved=(
                            urljoin(response_url, location)
                            if location and response.status in _REDIRECT_STATUSES
                            else None
                        ),
                        latencyMs=int((response_received - request_started) * 1000),
                        headers=_response_headers(headers),
                    ))
                except Exception:
                    continue
            return RedirectResult(
                input=url,
                hops=partial_hops,
                redirects=sum(h.status in _REDIRECT_STATUSES for h in partial_hops),
                finalUrl=partial_hops[-1].url if partial_hops else url,
                finalStatus=partial_hops[-1].status if partial_hops else None,
                error="Browser navigation failed.",
            )

    @staticmethod
    def _failed_result(
        input_url: str,
        hops: list[RedirectHop],
        final_url: str,
        error: str,
    ) -> RedirectResult:
        return RedirectResult(
            input=input_url,
            hops=hops,
            redirects=sum(h.status in _REDIRECT_STATUSES for h in hops),
            finalUrl=final_url,
            finalStatus=hops[-1].status if hops else None,
            error=error,
        )
