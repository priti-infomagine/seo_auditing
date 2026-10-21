"""Link checker for external URLs and uncrawled internal URLs.

HEAD first, fallback to streamed GET (no body read). Per-host semaphore
plus global semaphore. Manual redirect following with loop detection.
SSRF validation before every request and redirect hop.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse

import httpx

from app.core.config import settings
from app.core.logger import logger
from app.modules.crawler.utils.url import validate_url_ssrf_async
from app.shared.utils.url_utils import normalize_host, normalize_url

from .constants import UNVERIFIED_STATUS_CODES, USER_AGENT
from .graph import CheckResult, LinkStatusClass, RedirectInfo


@dataclass
class LinkChecker:
    """Check HTTP status for URLs not crawled during the main crawl."""

    timeout: float = field(default_factory=lambda: settings.LINK_CHECK_TIMEOUT)
    max_redirects: int = field(default_factory=lambda: settings.LINK_ANALYSIS_MAX_REDIRECT_HOPS)
    max_external: int = field(default_factory=lambda: settings.LINK_ANALYSIS_MAX_EXTERNAL_CHECKS)
    max_sitemap_only: int = field(default_factory=lambda: settings.LINK_ANALYSIS_MAX_SITEMAP_ONLY_CHECKS)

    global_semaphore: asyncio.Semaphore = field(init=False)
    _per_host_sems: Dict[str, asyncio.Semaphore] = field(default_factory=dict)

    def __post_init__(self):
        self.global_semaphore = asyncio.Semaphore(
            settings.LINK_ANALYSIS_CRAWL_CONCURRENCY
        )

    def _host_semaphore(self, host: str) -> asyncio.Semaphore:
        if host not in self._per_host_sems:
            self._per_host_sems[host] = asyncio.Semaphore(
                settings.LINK_ANALYSIS_PER_HOST_CONCURRENCY
            )
        return self._per_host_sems[host]

    @staticmethod
    def _normalize_target(url: str) -> Optional[str]:
        try:
            return normalize_url(url)
        except Exception:
            return None

    @staticmethod
    def _should_skip(url: str) -> bool:
        parsed = urlparse(url)
        scheme = parsed.scheme.lower()
        if scheme not in ("http", "https"):
            return True
        if parsed.fragment:
            return True
        return False

    async def check_urls(self, urls: Set[str]) -> Dict[str, CheckResult]:
        """Check a set of URLs concurrently. Returns {url: CheckResult}."""
        to_check: List[str] = []
        for url in urls:
            if self._should_skip(url):
                continue
            normalized = self._normalize_target(url)
            if normalized:
                to_check.append(normalized)

        to_check = list(set(to_check))  # dedupe

        async with httpx.AsyncClient(
            timeout=self.timeout,
            follow_redirects=False,
            headers={"User-Agent": USER_AGENT},
        ) as client:
            tasks = [self._check_single(url, client) for url in to_check]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        checked: Dict[str, CheckResult] = {}
        for url, result in zip(to_check, results):
            if isinstance(result, Exception):
                checked[url] = CheckResult(
                    status_class=LinkStatusClass.UNVERIFIED,
                    status_code=0,
                    final_url=url,
                    redirect_chain=[],
                    error_type="exception",
                )
            else:
                checked[url] = result
        return checked

    async def _check_single(
        self,
        url: str,
        client: httpx.AsyncClient,
    ) -> CheckResult:
        """Check a single URL: HEAD first, then streamed GET on failure."""
        # SSRF check before first request
        try:
            await validate_url_ssrf_async(url, allow_private=False)
        except Exception:
            return CheckResult(
                status_class=LinkStatusClass.UNVERIFIED,
                status_code=0,
                final_url=url,
                redirect_chain=[],
                error_type="ssrf_blocked",
            )

        async with self.global_semaphore:
            parsed = urlparse(url)
            host = normalize_host(parsed.netloc)
            host_sem = self._host_semaphore(host)

            async with host_sem:
                return await self._check_with_redirects(url, client)

    async def _check_with_redirects(
        self,
        url: str,
        client: httpx.AsyncClient,
    ) -> CheckResult:
        """Follow redirects manually with SSRF checks on each hop."""
        redirect_chain: List[RedirectInfo] = []
        current_url = url
        seen_urls: Set[str] = {url}

        for _ in range(self.max_redirects + 1):
            # SSRF check on every hop
            try:
                await validate_url_ssrf_async(current_url, allow_private=False)
            except Exception:
                return CheckResult(
                    status_class=LinkStatusClass.UNVERIFIED,
                    status_code=0,
                    final_url=current_url,
                    redirect_chain=redirect_chain,
                    error_type="ssrf_blocked",
                )

            # Try HEAD first
            status_code, location, error_type = await self._do_head(client, current_url)

            # If HEAD failed with unrecoverable error, try streamed GET
            if status_code is None:
                status_code, location, error_type = await self._do_streamed_get(client, current_url)

            # Still failed
            if status_code is None:
                return CheckResult(
                    status_class=LinkStatusClass.UNVERIFIED,
                    status_code=0,
                    final_url=current_url,
                    redirect_chain=redirect_chain,
                    error_type=error_type or "connection_error",
                )

            # Handle redirect
            if status_code in (301, 302, 303, 307, 308) and location:
                redirect_chain.append(
                    RedirectInfo(
                        url=current_url,
                        status_code=status_code,
                        location=location,
                    )
                )
                current_url = urljoin(current_url, location)
                if current_url in seen_urls:
                    return CheckResult(
                        status_class=LinkStatusClass.REDIRECT,
                        status_code=status_code,
                        final_url=current_url,
                        redirect_chain=redirect_chain,
                        error_type="redirect_loop",
                    )
                seen_urls.add(current_url)
                continue

            # Non-redirect — classify
            if status_code in UNVERIFIED_STATUS_CODES:
                return CheckResult(
                    status_class=LinkStatusClass.UNVERIFIED,
                    status_code=status_code,
                    final_url=current_url,
                    redirect_chain=redirect_chain,
                    error_type=error_type,
                )

            if 200 <= status_code < 300:
                return CheckResult(
                    status_class=LinkStatusClass.OK,
                    status_code=status_code,
                    final_url=current_url,
                    redirect_chain=redirect_chain,
                    error_type=None,
                )

            if 300 <= status_code < 400:
                return CheckResult(
                    status_class=LinkStatusClass.REDIRECT,
                    status_code=status_code,
                    final_url=current_url,
                    redirect_chain=redirect_chain,
                    error_type=None,
                )

            # Confirmed broken: 4xx (after retry) or 5xx
            return CheckResult(
                status_class=LinkStatusClass.BROKEN,
                status_code=status_code,
                final_url=current_url,
                redirect_chain=redirect_chain,
                error_type=error_type,
            )

        # Max redirects exceeded
        return CheckResult(
            status_class=LinkStatusClass.REDIRECT,
            status_code=300,
            final_url=current_url,
            redirect_chain=redirect_chain,
            error_type="too_many_redirects",
        )

    async def _do_head(
        self,
        client: httpx.AsyncClient,
        url: str,
    ) -> Tuple[Optional[int], Optional[str], Optional[str]]:
        """Execute HEAD request. Returns (status_code, location, error_type)."""
        try:
            resp = await client.head(url)
            return resp.status_code, resp.headers.get("location"), None
        except httpx.TimeoutException:
            return None, None, "timeout"
        except httpx.HTTPError:
            return None, None, "connection_error"

    async def _do_streamed_get(
        self,
        client: httpx.AsyncClient,
        url: str,
    ) -> Tuple[Optional[int], Optional[str], Optional[str]]:
        """Execute streamed GET (no body read). Returns (status_code, location, error_type)."""
        try:
            req = client.build_request("GET", url)
            resp = await client.send(req, stream=True)
            try:
                return resp.status_code, resp.headers.get("location"), None
            finally:
                await resp.aclose()
        except httpx.TimeoutException:
            return None, None, "timeout"
        except httpx.HTTPError:
            return None, None, "connection_error"
