"""Full-site concurrent crawler for link analysis.

BFS crawl with a worker pool (asyncio.Queue + asyncio.Semaphore).
Respects robots.txt rules via ``protego``. Records a LinkGraph with
per-page metadata, per-edge details, and sitemap-only URL set.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

from protego import Protego

from app.core.config import settings
from app.core.logger import logger
from app.modules.crawler.services.fetch_service import FetchResult, fetch_page
from app.modules.crawler.services.site_discovery_service import (
    RobotsTxtEvidence,
    SiteDiscoveryResult,
    SiteDiscoveryService,
)
from app.modules.crawler.utils.url import validate_url_ssrf
from app.modules.parser.extractors.link_extractor import LinkExtractor
from app.modules.parser.services.document_parser_service import (
    DocumentContext,
    DocumentParserService,
)
from app.shared.utils.url_utils import is_same_site as check_same_site, normalize_host, normalize_url

from .constants import ASSET_EXTENSIONS, NON_HTTP_SCHEMES, USER_AGENT
from .graph import CheckResult, LinkEdge, LinkGraph, PageNode, RedirectInfo
from .model import LinkStatusClass


def _is_asset_url(url: str) -> bool:
    parsed = urlparse(url)
    path = parsed.path.lower()
    return any(path.endswith(ext) for ext in ASSET_EXTENSIONS)


def _is_robot_blocked(parser: Optional[Protego], url: str) -> bool:
    if parser is None:
        return False
    try:
        return not parser.can_fetch(USER_AGENT, url)
    except Exception:
        return False


def _classify_url(url: str, base_host: str) -> Tuple[bool, bool]:
    """Return (is_internal, is_http_s)."""
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    if scheme not in ("http", "https"):
        return False, False
    host = normalize_host(parsed.netloc)
    is_internal = (host == base_host) or check_same_site(parsed.netloc, base_host)
    return is_internal, True


def _should_skip_link(href: str) -> bool:
    if not href or not href.strip():
        return True
    if href.startswith("#"):
        return True
    colon_idx = href.find(":")
    if colon_idx > 0:
        scheme = href.split(":", 1)[0].lower()
        if scheme in NON_HTTP_SCHEMES:
            return True
    return False


def _redirect_info_from_fetch(fetch_result: FetchResult) -> List[RedirectInfo]:
    return [
        RedirectInfo(url=r.url, status_code=r.status_code, location=r.location)
        for r in fetch_result.redirect_chain
    ]


def _classify_fetch_status(result: FetchResult) -> LinkStatusClass:
    if result.status_code == 0:
        return LinkStatusClass.UNVERIFIED
    if 300 <= result.status_code < 400:
        return LinkStatusClass.REDIRECT
    if 200 <= result.status_code < 300:
        return LinkStatusClass.OK
    return LinkStatusClass.BROKEN


@dataclass
class CrawlState:
    """Mutable shared state across crawl workers."""

    graph: LinkGraph
    checked_urls: Dict[str, CheckResult] = field(default_factory=dict)
    seen: Set[str] = field(default_factory=set)
    pages_crawled: int = 0
    blocked_by_robots: int = 0
    assets_skipped: int = 0
    crawl_truncated: bool = False
    sitemap_urls: Set[str] = field(default_factory=set)


@dataclass
class CrawlResult:
    """Result of a full site crawl."""

    graph: LinkGraph
    checked_urls: Dict[str, CheckResult]
    sitemap_urls: Set[str]
    pages_crawled: int
    crawl_truncated: bool
    blocked_by_robots: int
    assets_skipped: int


class SiteCrawler:
    """Concurrent full-site crawler producing a LinkGraph."""

    def __init__(
        self,
        canonical_url: str,
        domain: str,
        max_pages: Optional[int] = None,
        progress_callback: Optional[Any] = None,
    ):
        self.canonical_url = canonical_url
        self.domain = domain
        self._custom_max_pages = max_pages
        self._progress_callback = progress_callback

    @property
    def page_timeout(self) -> float:
        return settings.LINK_ANALYSIS_PAGE_TIMEOUT

    @property
    def max_pages(self) -> int:
        return self._custom_max_pages or settings.LINK_ANALYSIS_MAX_PAGES

    @property
    def max_depth(self) -> int:
        return settings.LINK_ANALYSIS_MAX_DEPTH

    @property
    def concurrency(self) -> int:
        return settings.LINK_ANALYSIS_CRAWL_CONCURRENCY

    @property
    def progress_every(self) -> int:
        return settings.LINK_ANALYSIS_PROGRESS_EVERY

    async def discover(self) -> SiteDiscoveryResult:
        """Discover sitemaps and robots.txt for the target site."""
        discovery = SiteDiscoveryService(
            self.canonical_url,
            timeout=int(self.page_timeout),
            max_urls_per_sitemap=5000,
            max_total_page_urls=5000,
        )
        try:
            return await asyncio.wait_for(
                discovery.discover(),
                timeout=self.page_timeout * 5,
            )
        except Exception as exc:
            logger.warning(f"SiteCrawler: site discovery failed for {self.domain}: {exc}")
            return SiteDiscoveryResult(
                robots=RobotsTxtEvidence(
                    url=f"{self.canonical_url}/robots.txt", exists=False
                ),
                sitemaps=[],
                discovered_urls=[],
            )

    async def _safe_fetch(self, url: str) -> FetchResult:
        """Fetch with SSRF protection; returns zeroed result on SSRF block."""
        try:
            validate_url_ssrf(url, allow_private=False)
        except Exception as exc:
            logger.warning(f"SiteCrawler: SSRF blocked {url}: {exc}")
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
            )
        try:
            return await fetch_page(
                url,
                timeout=self.page_timeout,
                follow_redirects=True,
                max_redirects=settings.LINK_ANALYSIS_MAX_REDIRECT_HOPS,
                user_agent=USER_AGENT,
            )
        except Exception as exc:
            logger.warning(f"SiteCrawler: fetch failed for {url}: {exc}")
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
                error_type="fetch_error",
            )

    def _is_html_page(self, result: FetchResult) -> bool:
        ct = result.content_type
        return bool(ct) and ct in ("text/html", "application/xhtml+xml")

    def _make_check_result(self, result: FetchResult) -> CheckResult:
        return CheckResult(
            status_class=_classify_fetch_status(result),
            status_code=result.status_code,
            final_url=result.final_url or result.normalized_url,
            redirect_chain=_redirect_info_from_fetch(result),
            error_type=result.error_type if not result.success else None,
        )

    def _build_page_node(
        self,
        fetch_result: FetchResult,
        depth: int,
    ) -> PageNode:
        redirects = _redirect_info_from_fetch(fetch_result)
        return PageNode(
            url=fetch_result.normalized_url,
            final_url=fetch_result.final_url or fetch_result.normalized_url,
            status_code=fetch_result.status_code,
            content_type=fetch_result.content_type,
            depth=depth,
            redirect_chain=redirects,
            error_type=fetch_result.error_type if not fetch_result.success else None,
        )

    def _maybe_signal_progress(self, state: CrawlState, phase: str) -> None:
        if (
            self._progress_callback
            and state.pages_crawled % self.progress_every == 0
        ):
            self._progress_callback(
                phase,
                state.pages_crawled,
                len(state.graph.pages),
            )

    async def crawl(self) -> CrawlResult:
        """Execute the full BFS crawl starting from the homepage."""
        discovery = await self.discover()

        sitemap_urls: Set[str] = set()
        for sm in discovery.sitemaps:
            sitemap_urls.update(sm.urls)

        robot_parser: Optional[Protego] = None
        if discovery.robots.exists and discovery.robots.content:
            try:
                robot_parser = Protego.parse(discovery.robots.content)
            except Exception as exc:
                logger.warning(f"SiteCrawler: failed to parse robots.txt: {exc}")

        # Fetch homepage to determine base host (post-redirect)
        home_result = await self._safe_fetch(self.canonical_url)

        if home_result.status_code == 0 or home_result.error_type:
            base_host = normalize_host(urlparse(self.canonical_url).netloc)
        else:
            final = home_result.final_url or self.canonical_url
            base_host = normalize_host(urlparse(final).netloc)

        graph = LinkGraph(base_host=base_host, sitemap_urls=sitemap_urls)
        state = CrawlState(
            graph=graph,
            sitemap_urls=sitemap_urls,
        )

        # Seed: register homepage as seen and enqueue it
        home_final = home_result.final_url or self.canonical_url
        try:
            home_norm = normalize_url(home_final)
        except Exception:
            home_norm = home_final
        state.seen.add(home_norm)

        queue: asyncio.Queue = asyncio.Queue()
        await queue.put((home_final, 0))

        # Seed internal URLs discovered from sitemaps so all site pages get crawled and analyzed
        for s_url in sitemap_urls:
            is_internal, is_http = _classify_url(s_url, base_host)
            if is_internal and is_http:
                try:
                    s_norm = normalize_url(s_url)
                except Exception:
                    s_norm = s_url
                if s_norm not in state.seen and len(state.seen) < self.max_pages:
                    state.seen.add(s_norm)
                    await queue.put((s_norm, 1))

        semaphore = asyncio.Semaphore(self.concurrency)
        workers = [
            asyncio.create_task(self._worker(queue, state, robot_parser, semaphore))
            for _ in range(self.concurrency)
        ]

        await queue.join()

        for w in workers:
            w.cancel()
        await asyncio.gather(*workers, return_exceptions=True)

        return CrawlResult(
            graph=graph,
            checked_urls=state.checked_urls,
            sitemap_urls=sitemap_urls,
            pages_crawled=state.pages_crawled,
            crawl_truncated=state.crawl_truncated,
            blocked_by_robots=state.blocked_by_robots,
            assets_skipped=state.assets_skipped,
        )

    async def _worker(
        self,
        queue: asyncio.Queue,
        state: CrawlState,
        robot_parser: Optional[Protego],
        semaphore: asyncio.Semaphore,
    ) -> None:
        while True:
            url, depth = await queue.get()
            try:
                async with semaphore:
                    await self._process_url(url, depth, state, robot_parser, queue)
            except Exception as exc:
                logger.warning(f"SiteCrawler._worker: error processing {url}: {exc}")
            finally:
                queue.task_done()

    async def _process_url(
        self,
        url: str,
        depth: int,
        state: CrawlState,
        robot_parser: Optional[Protego],
        queue: asyncio.Queue,
    ) -> None:
        """Fetch a single URL, extract links, enqueue discovered internal links."""
        # Truncation check
        if state.pages_crawled >= self.max_pages:
            if len(state.graph.pages) >= self.max_pages and not state.crawl_truncated:
                state.crawl_truncated = bool(queue.qsize())
            return

        # Robots check — skip disallowed URLs (do NOT report as broken)
        if _is_robot_blocked(robot_parser, url):
            state.blocked_by_robots += 1
            return

        result = await self._safe_fetch(url)

        # Register checked result
        try:
            norm_url = normalize_url(result.normalized_url)
        except Exception:
            norm_url = result.normalized_url

        state.checked_urls[norm_url] = self._make_check_result(result)
        state.graph.pages[norm_url] = self._build_page_node(result, depth)
        state.pages_crawled += 1

        self._maybe_signal_progress(state, "crawling")

        # Only parse HTML pages for links
        if not result.success or not self._is_html_page(result):
            return

        if state.pages_crawled >= self.max_pages:
            state.crawl_truncated = bool(queue.empty())
            return

        # Parse and extract links from final_url (post-redirect)
        final_url = result.final_url or result.normalized_url
        html_str = result.content.decode("utf-8", errors="ignore")
        context = DocumentParserService().parse(html_str, final_url)
        links = LinkExtractor().extract(context)

        page_node = state.graph.pages.get(norm_url)
        if page_node is None:
            page_node = self._build_page_node(result, depth)
            state.graph.pages[norm_url] = page_node

        base_host = state.graph.base_host

        for link_data in links:
            href = link_data.href
            if _should_skip_link(href):
                continue

            absolute = link_data.absolute_url or href
            if not absolute:
                continue

            is_internal, is_http = _classify_url(absolute, base_host)
            if not is_http:
                continue

            # Robots check on target
            if _is_robot_blocked(robot_parser, absolute):
                state.blocked_by_robots += 1
                continue

            # Record edge
            try:
                target_norm = normalize_url(absolute)
            except Exception:
                target_norm = absolute

            edge = LinkEdge(
                source_url=norm_url,
                target_url=target_norm,
                anchor_text=link_data.text,
                rel=link_data.rel,
                is_internal=is_internal,
                href_raw=href,
            )
            state.graph.add_edge(edge)
            page_node.outgoing_edges.append(edge)

            # Skip assets — record as edge only (already done above)
            if _is_asset_url(target_norm):
                state.assets_skipped += 1
                continue

            # Enqueue internal URLs for crawling
            if not is_internal:
                continue
            if target_norm in state.seen:
                continue
            if depth + 1 >= self.max_depth:
                continue
            state.seen.add(target_norm)
            await queue.put((target_norm, depth + 1))
