"""
CrawlerService - high-level crawler service.

Wraps the new crawler services to crawl a single URL and persist the results
to disk in ``app/storage/crawler/<domain>/``.  Returns a dict that
the API layer and tests expect.
"""
import json
from collections import deque
from pathlib import Path
from typing import Optional

from app.core.datetime_utils import utc_now
from app.core.logger import logger
from app.modules.crawler.services.page_crawl_service import PageCrawlService, PageCrawlResult
from app.modules.crawler.services.site_discovery_service import SiteDiscoveryService
from app.modules.crawler.utils.url import normalize_url_canonical
from app.modules.crawler.utils.url_classifier import classify_url, UrlClassification
from app.shared.utils.url_utils import get_domain, normalize_url

# Project root is three levels above this file:
#   app/services/crawler/crawl_service.py -> app/ -> backend root
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_STORAGE_DIR = _PROJECT_ROOT / "app" / "storage" / "crawler"


class CrawlerService:
    """
    Service that crawls a URL, saves the result to storage,
    and returns a structured response dict.
    """

    def __init__(self, page_crawl_service: Optional[PageCrawlService] = None):
        self.page_crawl_service = page_crawl_service or PageCrawlService()

    async def crawl_url(self, url: str) -> dict:
        """
        Crawl a single URL, save results to storage, and return a
        structured dict.

        Args:
            url: URL to crawl (with or without protocol).

        Returns:
            Dict with keys: url, domain, test_number, file_path,
            crawled_at, data.

        Raises:
            ValueError: if the URL is invalid.
            RuntimeError: if the crawl fails.
        """
        # Normalise / validate
        normalized = normalize_url(url)
        domain = get_domain(normalized)
        if not domain:
            raise ValueError(f"Invalid URL: {url} - could not extract domain")

        # Crawl
        result: PageCrawlResult = await self.page_crawl_service.crawl_page(normalized)

        if result.error:
            raise RuntimeError(f"Crawl failed for {normalized}: {result.error}")

        # Determine incremental test number for this domain
        test_number = self._get_next_test_number(domain)

        # Build storage path and ensure the directory exists
        storage_path = self._get_storage_path(domain, test_number)
        storage_path.parent.mkdir(parents=True, exist_ok=True)

        # Save full crawl data to disk
        self._save_to_storage(result, storage_path, normalized, domain, test_number)

        crawled_at = utc_now().isoformat()

        # Build the response ``data`` dict
        data = {
            "requested_url": result.url,
            "final_url": result.fetch_result.final_url if result.fetch_result else result.url,
            "html": result.document.raw_html if result.document else "",
            "http": {
                "status_code": result.fetch_result.status_code if result.fetch_result else 0,
                "response_time": (result.fetch_result.response_time_ms / 1000.0) if result.fetch_result else 0,
                "response_time_ms": result.fetch_result.response_time_ms if result.fetch_result else 0,
                "content_type": result.fetch_result.content_type if result.fetch_result else "",
                "content_size": result.fetch_result.content_length if result.fetch_result else 0,
                "headers": result.fetch_result.headers if result.fetch_result else {},
            },
        }
        data["status_code"] = data["http"]["status_code"]
        data["response_time"] = data["http"]["response_time"]
        data["html_size"] = data["http"]["content_size"]

        return {
            "url": normalized,
            "domain": domain,
            "test_number": test_number,
            "file_path": str(storage_path),
            "crawled_at": crawled_at,
            "data": data,
        }

    # -- multi-page crawling ------------------------------------------------

    async def crawl_site(
        self,
        start_url: str,
        max_pages: int = 1000,
        max_depth: int = 3,
    ) -> list[dict]:
        """
        DEPRECATED: superseded by CrawlOrchestrator (see
        app/modules/crawler/services/crawl_orchestrator.py), used by
        /api/v1/audit/analyze. Kept only for backward compatibility with
        app/modules/crawler/tests/unit/test_crawl_site.py. Do not wire new
        endpoints to this method.

        Discover and crawl pages from ``start_url`` using a sitemap-first,
        BFS-fallback strategy.

        Phase 1 — sitemap discovery: uses ``SiteDiscoveryService`` to fetch
        robots.txt and sitemap(s), extracting up to ``max_pages`` URLs.

        Phase 2 — BFS link discovery: if the sitemap yielded fewer than
        ``max_pages`` URLs (or none), the start page is crawled and
        ``URLDiscoverer.discover_from_html`` is used to traverse internal
        links up to ``max_depth`` hops.

        Each discovered URL is then crawled via the existing
        ``crawl_url()`` method.  The start URL is always crawled first.

        Reuses existing crawler utilities — no sitemap/URL-discovery logic
        is duplicated.

        Args:
            start_url: Seed URL to begin crawling from.
            max_pages: Hard cap on the total number of pages to crawl.
            max_depth: Maximum link-hops from the start URL to follow.

        Returns:
            List of crawl_result dicts (same shape as ``crawl_url()``),
            one per successfully crawled URL.
        """
        normalized = normalize_url(start_url)
        domain = get_domain(normalized)
        if not domain:
            raise ValueError(f"Invalid URL: {start_url} - could not extract domain")

        visited: set[str] = set()
        crawl_results: list[dict] = []
        queue: deque[tuple[str, int]] = deque()

        # --- Phase 1: Sitemap-based discovery ---
        sitemap_urls = await self._discover_sitemap_urls(normalized, domain, max_pages)

        if sitemap_urls:
            for url in sitemap_urls:
                if len(queue) >= max_pages:
                    break
                norm = normalize_url_canonical(url)
                if norm not in visited:
                    visited.add(norm)
                    queue.append((url, 0))

        # --- Phase 2: BFS fallback (seed + internal links) ---
        seed_norm = normalize_url_canonical(normalized)
        if seed_norm not in visited:
            visited.add(seed_norm)
            queue.append((normalized, 0))

        # BFS traversal: crawl each queued URL, extract links, enqueue new ones
        while queue and len(crawl_results) < max_pages:
            url, depth = queue.popleft()

            # Normalize for crawl_url (it handles normalization internally too)
            try:
                result = await self.crawl_url(url)
            except Exception:
                continue

            crawl_results.append(result)

            # If we haven't hit the cap and can go deeper, discover links
            if len(crawl_results) < max_pages and depth < max_depth:
                html = result["data"].get("html", "")
                if html:
                    page_url = result["url"]
                    discovered = self._discover_links_from_html(html, page_url, domain, depth)
                    for d in discovered:
                        if len(visited) >= max_pages:
                            break
                        norm = normalize_url_canonical(d.normalized_url)
                        if norm not in visited:
                            visited.add(norm)
                            queue.append((d.normalized_url, depth + 1))

        return crawl_results

    # -- private helpers ------------------------------------------------
    async def _discover_sitemap_urls(
        self,
        start_url: str,
        domain: str,
        max_pages: int,
    ) -> list[str]:
        """
        Use SiteDiscoveryService to fetch robots.txt + sitemap(s) and return
        same-domain URLs extracted from sitemaps.
        """
        sitemap_urls: list[str] = []
        try:
            discovery = SiteDiscoveryService(start_url)
            result = await discovery.discover()
            for url in result.discovered_urls[:max_pages]:
                try:
                    classification, _ = classify_url(url, base_domain=domain)
                    if classification == UrlClassification.HTML:
                        sitemap_urls.append(url)
                except Exception:
                    continue
        except Exception as exc:
            logger.warning(
                "CrawlerService._discover_sitemap_urls: "
                "sitemap/robots discovery failed for %s: %s "
                "— falling back to BFS link discovery",
                start_url, exc,
            )
        return sitemap_urls

    def _discover_links_from_html(
        self,
        html: str,
        source_url: str,
        base_domain: str,
        depth: int,
    ) -> list:
        """Use URLDiscoverer to extract internal URLs from a page's HTML."""
        from app.modules.crawler.utils.url_discoverer import URLDiscoverer

        discoverer = URLDiscoverer()
        return discoverer.discover_from_html(
            html=html,
            source_url=source_url,
            base_domain=base_domain,
            depth=depth,
        )

    def _get_next_test_number(self, domain: str) -> int:
        """Find the next incremental test number for a domain."""
        domain_dir = _STORAGE_DIR / domain
        if not domain_dir.exists():
            return 1
        existing = sorted(domain_dir.glob(f"{domain}_test_*.json"))
        if not existing:
            return 1
        max_num = 0
        for f in existing:
            name = f.stem
            parts = name.rsplit("_test_", 1)
            if len(parts) == 2:
                try:
                    max_num = max(max_num, int(parts[1]))
                except ValueError:
                    continue
        return max_num + 1

    def _get_storage_path(self, domain: str, test_number: int) -> Path:
        """Build the storage file path for a given domain + test number."""
        filename = f"{domain}_test_{test_number}.json"
        return _STORAGE_DIR / domain / filename

    def _save_to_storage(
        self,
        result: PageCrawlResult,
        storage_path: Path,
        requested_url: str,
        domain: str,
        test_number: int,
    ) -> None:
        """Write the crawl result to a JSON file on disk."""
        payload = {
            "requested_url": result.url,
            "final_url": result.fetch_result.final_url if result.fetch_result else result.url,
            "html": result.document.raw_html if result.document else "",
            "http": {
                "status_code": result.fetch_result.status_code if result.fetch_result else 0,
                "response_time": (result.fetch_result.response_time_ms / 1000.0) if result.fetch_result else 0,
                "response_time_ms": result.fetch_result.response_time_ms if result.fetch_result else 0,
                "content_type": result.fetch_result.content_type if result.fetch_result else "",
                "content_size": result.fetch_result.content_length if result.fetch_result else 0,
                "headers": result.fetch_result.headers if result.fetch_result else {},
            },
        }
        payload["domain"] = domain
        payload["test_number"] = test_number
        payload["crawled_at"] = utc_now().isoformat()

        with open(storage_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
