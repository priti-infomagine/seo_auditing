"""
Integration tests for CrawlScheduler diagnostics, sitemap URL submission,
max_pages / max_depth caps, and deduplication.

All tests use mock worker functions — no real network requests are made.
"""
import asyncio
import sys
from pathlib import Path
from typing import List

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest

from app.modules.crawler.config import CrawlConfig
from app.modules.crawler.services.crawl_scheduler import CrawlScheduler
from app.modules.crawler.types import DiscoveredURL


def _make_config(**kwargs):
    defaults = dict(max_depth=5, max_pages=100, http_concurrency=1, browser_concurrency=1)
    defaults.update(kwargs)
    return CrawlConfig(**defaults)


def _worker_factory(crawled: List[str], discover_fn=None):
    """Create a worker that records crawled URLs and optionally discovers links."""

    async def worker(item: DiscoveredURL, http_sem, browser_sem):
        crawled.append(item.normalized_url)
        if discover_fn:
            discover_fn(item, crawled)

    return worker


class TestSchedulerDiagnostics:
    """Verify rejection diagnostics are tracked correctly."""

    @pytest.mark.asyncio
    async def test_external_host_rejected(self):
        scheduler = CrawlScheduler(
            config=_make_config(),
            worker_func=_worker_factory([]),
            base_domain="example.com",
        )
        result = scheduler.submit_discovered_url(
            url="https://external.com/page",
            source_url="https://example.com/",
            source_type="html_link",
            depth=1,
        )
        assert result is False
        assert scheduler.url_diagnostics["external_host"] == 1

    @pytest.mark.asyncio
    async def test_duplicate_rejected(self):
        scheduler = CrawlScheduler(
            config=_make_config(),
            worker_func=_worker_factory([]),
            base_domain="example.com",
        )
        r1 = scheduler.submit_discovered_url(
            url="https://example.com/page1",
            source_url="https://example.com/",
            source_type="html_link",
            depth=1,
        )
        assert r1 is True
        r2 = scheduler.submit_discovered_url(
            url="https://example.com/page1",
            source_url="https://example.com/",
            source_type="html_link",
            depth=1,
        )
        assert r2 is False
        assert scheduler.url_diagnostics["duplicate"] == 1

    @pytest.mark.asyncio
    async def test_resource_rejected(self):
        scheduler = CrawlScheduler(
            config=_make_config(),
            worker_func=_worker_factory([]),
            base_domain="example.com",
        )
        result = scheduler.submit_discovered_url(
            url="https://example.com/style.css",
            source_url="https://example.com/",
            source_type="html_link",
            depth=1,
        )
        assert result is False
        assert scheduler.url_diagnostics["resource"] == 1

    @pytest.mark.asyncio
    async def test_api_rejected(self):
        scheduler = CrawlScheduler(
            config=_make_config(),
            worker_func=_worker_factory([]),
            base_domain="example.com",
        )
        result = scheduler.submit_discovered_url(
            url="https://example.com/api/v1/users",
            source_url="https://example.com/",
            source_type="html_link",
            depth=1,
        )
        assert result is False
        assert scheduler.url_diagnostics["api"] == 1

    @pytest.mark.asyncio
    async def test_invalid_url_rejected(self):
        scheduler = CrawlScheduler(
            config=_make_config(),
            worker_func=_worker_factory([]),
            base_domain="example.com",
        )
        result = scheduler.submit_discovered_url(
            url="mailto:test@example.com",
            source_url="https://example.com/",
            source_type="html_link",
            depth=1,
        )
        assert result is False
        assert scheduler.url_diagnostics["invalid_url"] == 1

    @pytest.mark.asyncio
    async def test_non_html_rejected(self):
        scheduler = CrawlScheduler(
            config=_make_config(),
            worker_func=_worker_factory([]),
            base_domain="example.com",
        )
        result = scheduler.submit_discovered_url(
            url="https://example.com/sitemap.xml",
            source_url="https://example.com/",
            source_type="html_link",
            depth=1,
        )
        assert result is False
        assert scheduler.url_diagnostics["non_html"] == 1

    @pytest.mark.asyncio
    async def test_max_depth_rejected(self):
        scheduler = CrawlScheduler(
            config=_make_config(max_depth=2),
            worker_func=_worker_factory([]),
            base_domain="example.com",
        )
        result = scheduler.submit_discovered_url(
            url="https://example.com/page",
            source_url="https://example.com/",
            source_type="html_link",
            depth=3,
        )
        assert result is False
        assert scheduler.url_diagnostics["max_depth"] == 1

    @pytest.mark.asyncio
    async def test_max_pages_rejected(self):
        scheduler = CrawlScheduler(
            config=_make_config(max_pages=3),
            worker_func=_worker_factory([]),
            base_domain="example.com",
        )
        for i in range(3):
            scheduler.submit_discovered_url(
                url=f"https://example.com/page{i}",
                source_url="https://example.com/",
                source_type="html_link",
                depth=1,
            )
        result = scheduler.submit_discovered_url(
            url="https://example.com/page3",
            source_url="https://example.com/",
            source_type="html_link",
            depth=1,
        )
        assert result is False
        assert scheduler.url_diagnostics["max_pages"] == 1

    @pytest.mark.asyncio
    async def test_diagnostics_initialized_to_zero(self):
        scheduler = CrawlScheduler(
            config=_make_config(),
            worker_func=_worker_factory([]),
            base_domain="example.com",
        )
        for key in ("external_host", "duplicate", "non_html", "resource", "api",
                     "max_depth", "max_pages", "invalid_url", "robots_blocked"):
            assert scheduler.url_diagnostics[key] == 0

    @pytest.mark.asyncio
    async def test_mixed_rejections_counted_separately(self):
        """Each rejected URL increments only its own counter."""
        scheduler = CrawlScheduler(
            config=_make_config(max_depth=2, max_pages=100),
            worker_func=_worker_factory([]),
            base_domain="example.com",
        )
        # external
        scheduler.submit_discovered_url("https://external.com/p", "https://example.com/", "html_link", 1)
        # resource
        scheduler.submit_discovered_url("https://example.com/img.png", "https://example.com/", "html_link", 1)
        # api
        scheduler.submit_discovered_url("https://example.com/api/x", "https://example.com/", "html_link", 1)
        # max_depth
        scheduler.submit_discovered_url("https://example.com/deep", "https://example.com/", "html_link", 5)
        # valid URL
        scheduler.submit_discovered_url("https://example.com/valid", "https://example.com/", "html_link", 1)

        diag = scheduler.url_diagnostics
        assert diag["external_host"] == 1
        assert diag["resource"] == 1
        assert diag["api"] == 1
        assert diag["max_depth"] == 1
        assert diag["duplicate"] == 0
        assert diag["invalid_url"] == 0


class TestSitemapUrlSubmission:
    """Sitemap-discovered page URLs enter the crawl queue."""

    @pytest.mark.asyncio
    async def test_sitemap_urls_enter_queue(self):
        crawled = []
        scheduler = CrawlScheduler(
            config=_make_config(http_concurrency=2),
            worker_func=_worker_factory(crawled),
            base_domain="example.com",
        )
        scheduler.submit_seed("https://example.com/")
        submitted = scheduler.submit_sitemap_urls([
            "https://example.com/page1",
            "https://example.com/page2",
            "https://example.com/page3",
        ])
        assert submitted == 3
        await scheduler.run()
        assert "https://example.com/page1" in crawled
        assert "https://example.com/page2" in crawled
        assert "https://example.com/page3" in crawled

    @pytest.mark.asyncio
    async def test_sitemap_urls_marked_sitemap_source(self):
        seen = []

        async def worker(item, http_sem, browser_sem):
            seen.append((item.normalized_url, item.source_type))

        scheduler = CrawlScheduler(
            config=_make_config(),
            worker_func=worker,
            base_domain="example.com",
        )
        scheduler.submit_seed("https://example.com/")
        scheduler.submit_sitemap_urls(
            ["https://example.com/sitemap-page"],
            source_url="https://example.com/sitemap.xml",
        )
        await scheduler.run()
        sitemap_sources = [s for url, s in seen if url == "https://example.com/sitemap-page"]
        assert "sitemap" in sitemap_sources

    @pytest.mark.asyncio
    async def test_sitemap_xml_not_crawled(self):
        crawled = []
        scheduler = CrawlScheduler(
            config=_make_config(),
            worker_func=_worker_factory(crawled),
            base_domain="example.com",
        )
        scheduler.submit_seed("https://example.com/")
        submitted = scheduler.submit_sitemap_urls([
            "https://example.com/sitemap.xml",
            "https://example.com/page1",
        ])
        assert submitted == 1
        assert scheduler.url_diagnostics["non_html"] == 1
        await scheduler.run()
        assert "https://example.com/sitemap.xml" not in crawled
        assert "https://example.com/page1" in crawled

    @pytest.mark.asyncio
    async def test_sitemap_dedup_with_html_links(self):
        """A URL discovered via both sitemap and HTML link is crawled once."""
        crawled = []

        def discover(item, crawled_list):
            if item.normalized_url == "https://example.com/":
                scheduler.submit_discovered_url(
                    url="https://example.com/dup-page",
                    source_url=item.normalized_url,
                    source_type="html_link",
                    depth=1,
                )

        scheduler = CrawlScheduler(
            config=_make_config(),
            worker_func=_worker_factory(crawled, discover),
            base_domain="example.com",
        )
        scheduler.submit_seed("https://example.com/")
        scheduler.submit_sitemap_urls(["https://example.com/dup-page"])
        await scheduler.run()
        assert crawled.count("https://example.com/dup-page") == 1
        assert scheduler.url_diagnostics["duplicate"] == 1

    @pytest.mark.asyncio
    async def test_sitemap_urls_www_to_apex(self):
        """www. variant sitemap URLs are accepted when base is apex."""
        crawled = []
        scheduler = CrawlScheduler(
            config=_make_config(),
            worker_func=_worker_factory(crawled),
            base_domain="example.com",
        )
        scheduler.submit_seed("https://example.com/")
        submitted = scheduler.submit_sitemap_urls([
            "https://www.example.com/page1",
        ])
        assert submitted == 1
        await scheduler.run()
        assert "https://www.example.com/page1" in crawled

    @pytest.mark.asyncio
    async def test_sitemap_urls_apex_to_www(self):
        """Apex sitemap URLs are accepted when base is www."""
        crawled = []
        scheduler = CrawlScheduler(
            config=_make_config(),
            worker_func=_worker_factory(crawled),
            base_domain="www.example.com",
        )
        scheduler.submit_seed("https://www.example.com/")
        submitted = scheduler.submit_sitemap_urls([
            "https://example.com/page1",
        ])
        assert submitted == 1
        await scheduler.run()
        assert "https://example.com/page1" in crawled

    @pytest.mark.asyncio
    async def test_sitemap_urls_subdomain_rejected(self):
        """Arbitrary subdomain sitemap URLs are rejected as external."""
        crawled = []
        scheduler = CrawlScheduler(
            config=_make_config(),
            worker_func=_worker_factory(crawled),
            base_domain="example.com",
        )
        scheduler.submit_seed("https://example.com/")
        submitted = scheduler.submit_sitemap_urls([
            "https://blog.example.com/post1",
            "https://example.com/page1",
        ])
        assert submitted == 1  # only the same-site URL
        assert scheduler.url_diagnostics["external_host"] == 1
        await scheduler.run()
        assert "https://blog.example.com/post1" not in crawled
        assert "https://example.com/page1" in crawled


class TestSchedulerMaxLimits:
    """max_pages and max_depth cap the crawl correctly."""

    @pytest.mark.asyncio
    async def test_max_pages_hard_cap(self):
        """max_pages is a hard upper bound — no more pages are crawled."""
        crawled = []
        scheduler = CrawlScheduler(
            config=_make_config(max_pages=3),
            worker_func=_worker_factory(crawled),
            base_domain="example.com",
        )
        for i in range(10):
            scheduler.submit_seed(f"https://example.com/p{i}")
        await scheduler.run()
        assert len(crawled) == 3

    @pytest.mark.asyncio
    async def test_max_depth_stops_traversal(self):
        """Links at depth > max_depth are rejected, not crawled."""
        crawled = []

        def discover(item, crawled_list):
            if item.depth < 10:
                scheduler.submit_discovered_url(
                    url=f"https://example.com/deeper-{item.depth + 1}",
                    source_url=item.normalized_url,
                    source_type="html_link",
                    depth=item.depth + 1,
                )

        scheduler = CrawlScheduler(
            config=_make_config(max_depth=2),
            worker_func=_worker_factory(crawled, discover),
            base_domain="example.com",
        )
        scheduler.submit_seed("https://example.com/")
        await scheduler.run()
        # depth 0 (seed), depth 1, depth 2 = 3 crawled
        assert len(crawled) == 3
        assert scheduler.url_diagnostics["max_depth"] >= 1

    @pytest.mark.asyncio
    async def test_pages_failed_count_tracked(self):
        """Workers returning False increment pages_failed_count, not pages_crawled_count."""

        async def failing_worker(item, http_sem, browser_sem):
            return False

        scheduler = CrawlScheduler(
            config=_make_config(max_pages=5),
            worker_func=failing_worker,
            base_domain="example.com",
        )
        for i in range(3):
            scheduler.submit_seed(f"https://example.com/p{i}")
        await scheduler.run()

        assert scheduler.pages_crawled_count == 0
        assert scheduler.pages_failed_count == 3

    @pytest.mark.asyncio
    async def test_max_pages_counts_successful_crawls_only(self):
        """max_pages is a hard limit on successful crawls, not total attempts."""

        async def mixed_worker(item, http_sem, browser_sem):
            return item.normalized_url.endswith("ok") or item.normalized_url.endswith("success")

        scheduler = CrawlScheduler(
            config=_make_config(max_pages=2),
            worker_func=mixed_worker,
            base_domain="example.com",
        )
        scheduler.submit_seed("https://example.com/ok")
        scheduler.submit_seed("https://example.com/fail1")
        scheduler.submit_seed("https://example.com/fail2")
        scheduler.submit_seed("https://example.com/success")
        await scheduler.run()

        assert scheduler.pages_crawled_count == 2
        assert scheduler.pages_failed_count == 2


class TestSetBaseDomain:
    """Verify set_base_domain normalizes www and updates classification."""

    def test_set_base_domain_normalizes_www(self):
        scheduler = CrawlScheduler(
            config=_make_config(),
            worker_func=_worker_factory([]),
            base_domain="www.example.com",
        )
        assert scheduler.base_domain == "example.com"

    def test_set_base_domain_from_url_apex_to_www(self):
        scheduler = CrawlScheduler(
            config=_make_config(),
            worker_func=_worker_factory([]),
            base_domain="example.com",
        )
        scheduler.set_base_domain_from_url("https://www.example.com/home")
        assert scheduler.base_domain == "example.com"

    def test_set_base_domain_from_url_www_to_apex(self):
        scheduler = CrawlScheduler(
            config=_make_config(),
            worker_func=_worker_factory([]),
            base_domain="www.example.com",
        )
        scheduler.set_base_domain_from_url("https://example.com/home")
        assert scheduler.base_domain == "example.com"

    def test_set_base_domain_from_url_https(self):
        scheduler = CrawlScheduler(
            config=_make_config(),
            worker_func=_worker_factory([]),
            base_domain="example.com",
        )
        scheduler.set_base_domain_from_url("https://example.com/home")
        assert scheduler.base_domain == "example.com"

    def test_set_base_domain_strips_port(self):
        scheduler = CrawlScheduler(
            config=_make_config(),
            worker_func=_worker_factory([]),
            base_domain="example.com",
        )
        scheduler.set_base_domain_from_url("https://example.com:8080/home")
        assert scheduler.base_domain == "example.com"

    @pytest.mark.asyncio
    async def test_base_domain_normalization_accepts_www(self):
        """With base_domain normalized, www URLs pass without set_base_domain."""
        crawler = CrawlScheduler(
            config=_make_config(),
            worker_func=_worker_factory([]),
            base_domain="example.com",
        )
        result = crawler.submit_discovered_url(
            url="https://www.example.com/page",
            source_url="https://example.com/",
            source_type="html_link",
            depth=1,
        )
        assert result is True
        assert crawler.url_diagnostics["external_host"] == 0

    @pytest.mark.asyncio
    async def test_set_base_domain_allows_cross_variant(self):
        """After set_base_domain('example.com'), a www URL is accepted."""
        scheduler = CrawlScheduler(
            config=_make_config(),
            worker_func=_worker_factory([]),
            base_domain="www.example.com",
        )
        scheduler.set_base_domain("example.com")
        result = scheduler.submit_discovered_url(
            url="https://www.example.com/page",
            source_url="https://example.com/",
            source_type="html_link",
            depth=1,
        )
        assert result is True
