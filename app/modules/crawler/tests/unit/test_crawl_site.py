"""
Tests for CrawlerService.crawl_site() — multi-page discovery and crawling.

Tests:
- Sitemap-based discovery
- Link-based fallback discovery (BFS)
- max_pages cap enforcement
- max_depth cap enforcement
- Dedup of already-visited URLs
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from urllib.parse import urlparse

from app.modules.crawler.crawl_service import CrawlerService
from app.modules.crawler.types import DiscoveredURL
from app.modules.crawler.utils.url import normalize_url_canonical


def _make_crawl_result(url: str, html: str = "", status_code: int = 200) -> dict:
    """Create a fake crawl result dict (same shape as crawl_url() returns)."""
    return {
        "url": url,
        "domain": "example.com",
        "test_number": 1,
        "file_path": f"/tmp/example.com_test_1.json",
        "crawled_at": "2026-01-01T00:00:00Z",
        "data": {
            "html": html,
            "http": {
                "status_code": status_code,
                "response_time": 0.05,
                "response_time_ms": 50,
                "content_type": "text/html",
                "content_size": len(html),
                "headers": {},
            },
        },
    }


def _make_discovered_url(url: str, depth: int = 0) -> DiscoveredURL:
    return DiscoveredURL(
        url=url,
        normalized_url=normalize_url_canonical(url),
        source_url="https://example.com",
        source_type="html_link",
        depth=depth,
    )


def _make_service():
    """Create a CrawlerService with __init__ bypassed for mocking."""
    return CrawlerService.__new__(CrawlerService)


class TestCrawlSiteSitemapDiscovery:
    """Sitemap-based URL discovery."""

    @pytest.mark.asyncio
    async def test_sitemap_based_discovery(self):
        """Sitemap URLs are crawled when discovered from SiteDiscoveryService."""
        service = _make_service()

        sitemap_urls = [
            "https://example.com/",
            "https://example.com/about",
            "https://example.com/contact",
        ]
        service._discover_sitemap_urls = AsyncMock(return_value=sitemap_urls)
        service._discover_links_from_html = MagicMock(return_value=[])

        crawl_results = []

        async def mock_crawl_url(url, **kwargs):
            result = _make_crawl_result(url, html="<html></html>")
            crawl_results.append(result)
            return result

        service.crawl_url = mock_crawl_url

        results = await service.crawl_site(
            "https://example.com", max_pages=10, max_depth=2
        )

        assert len(results) == 3
        urls = [r["url"] for r in results]
        assert "https://example.com/" in urls
        assert "https://example.com/about" in urls
        assert "https://example.com/contact" in urls
        service._discover_sitemap_urls.assert_called_once()


class TestCrawlSiteLinkDiscovery:
    """BFS link-based fallback discovery."""

    @pytest.mark.asyncio
    async def test_link_based_fallback_discovery(self):
        """When sitemap is empty, BFS discovers links from crawled HTML."""
        service = _make_service()

        service._discover_sitemap_urls = AsyncMock(return_value=[])

        crawl_count = 0

        async def mock_crawl_url(url, **kwargs):
            nonlocal crawl_count
            crawl_count += 1
            if crawl_count == 1:
                html = '<html><body><a href="/about">About</a></body></html>'
            else:
                html = "<html></html>"
            return _make_crawl_result(url, html=html)

        service.crawl_url = mock_crawl_url

        def mock_discover_links(html, source_url, base_domain, depth):
            if "about" in html:
                return [_make_discovered_url("https://example.com/about", depth=depth)]
            return []

        service._discover_links_from_html = mock_discover_links

        results = await service.crawl_site(
            "https://example.com", max_pages=10, max_depth=2
        )

        assert len(results) == 2
        assert results[0]["url"] == "https://example.com/"
        assert results[1]["url"] == "https://example.com/about"

    @pytest.mark.asyncio
    async def test_bfs_traverses_multiple_levels(self):
        """Links discovered on sub-pages are crawled when within depth limit."""
        service = _make_service()

        service._discover_sitemap_urls = AsyncMock(return_value=[])
        service._discover_links_from_html = MagicMock(return_value=[])

        crawl_results = []

        async def mock_crawl_url(url, **kwargs):
            result = _make_crawl_result(url, html="<html></html>")
            crawl_results.append(result)
            return result

        service.crawl_url = mock_crawl_url

        # Simulate _discover_links_from_html returning links based on URL
        def mock_discover(html, source_url, base_domain, depth):
            parsed = urlparse(source_url)
            path = parsed.path
            if path == "/" and depth < 2:
                return [
                    _make_discovered_url("https://example.com/level1", depth=depth),
                ]
            if path == "/level1" and depth < 2:
                return [
                    _make_discovered_url("https://example.com/level2", depth=depth),
                ]
            return []

        service._discover_links_from_html = mock_discover

        results = await service.crawl_site(
            "https://example.com", max_pages=10, max_depth=3
        )

        urls = [r["url"] for r in results]
        assert "https://example.com/" in urls
        assert "https://example.com/level1" in urls
        assert "https://example.com/level2" in urls


class TestCrawlSiteMaxPages:
    """max_pages cap enforcement."""

    @pytest.mark.asyncio
    async def test_max_pages_cap_enforcement(self):
        """Crawling stops when max_pages is reached, even if more URLs discovered."""
        service = _make_service()

        service._discover_sitemap_urls = AsyncMock(return_value=[])

        async def mock_crawl_url(url, **kwargs):
            html = (
                '<html><body>'
                '<a href="/p1">P1</a>'
                '<a href="/p2">P2</a>'
                '<a href="/p3">P3</a>'
                '</body></html>'
            )
            return _make_crawl_result(url, html=html)

        service.crawl_url = mock_crawl_url

        def mock_discover(html, source_url, base_domain, depth):
            return [
                _make_discovered_url("https://example.com/p1", depth=depth),
                _make_discovered_url("https://example.com/p2", depth=depth),
                _make_discovered_url("https://example.com/p3", depth=depth),
            ]

        service._discover_links_from_html = mock_discover

        results = await service.crawl_site(
            "https://example.com", max_pages=2, max_depth=3
        )

        assert len(results) == 2


class TestCrawlSiteMaxDepth:
    """max_depth cap enforcement."""

    @pytest.mark.asyncio
    async def test_max_depth_zero(self):
        """With max_depth=0, only the start page is crawled."""
        service = _make_service()

        service._discover_sitemap_urls = AsyncMock(return_value=[])

        async def mock_crawl_url(url, **kwargs):
            html = '<html><body><a href="/about">About</a></body></html>'
            return _make_crawl_result(url, html=html)

        service.crawl_url = mock_crawl_url
        service._discover_links_from_html = MagicMock(return_value=[])

        results = await service.crawl_site(
            "https://example.com", max_pages=10, max_depth=0
        )

        assert len(results) == 1
        assert results[0]["url"] == "https://example.com/"
        # Links should not be discovered when depth limit is 0
        service._discover_links_from_html.assert_not_called()

    @pytest.mark.asyncio
    async def test_max_depth_one(self):
        """With max_depth=1, start page + 1 level of links are crawled."""
        service = _make_service()

        service._discover_sitemap_urls = AsyncMock(return_value=[])

        crawl_count = 0

        async def mock_crawl_url(url, **kwargs):
            nonlocal crawl_count
            crawl_count += 1
            if crawl_count == 1:
                html = '<html><body><a href="/l1">L1</a></body></html>'
            else:
                html = '<html><body><a href="/l2">L2</a></body></html>'
            return _make_crawl_result(url, html=html)

        service.crawl_url = mock_crawl_url

        def mock_discover(html, source_url, base_domain, depth):
            if "/l1" not in source_url:
                return [_make_discovered_url("https://example.com/l1", depth=depth)]
            return []  # Don't discover from l1 page

        service._discover_links_from_html = mock_discover

        results = await service.crawl_site(
            "https://example.com", max_pages=10, max_depth=1
        )

        urls = [r["url"] for r in results]
        assert "https://example.com/" in urls
        assert "https://example.com/l1" in urls
        assert "https://example.com/l2" not in urls  # Should not reach depth 2


class TestCrawlSiteDedup:
    """Dedup of already-visited URLs."""

    @pytest.mark.asyncio
    async def test_dedup_visited_urls(self):
        """URLs discovered multiple times across pages are only crawled once."""
        service = _make_service()

        service._discover_sitemap_urls = AsyncMock(return_value=[])

        async def mock_crawl_url(url, **kwargs):
            html = (
                '<html><body>'
                '<a href="/about">About</a>'
                '<a href="/contact">Contact</a>'
                '<a href="/">Home</a>'
                '</body></html>'
            )
            return _make_crawl_result(url, html=html)

        service.crawl_url = mock_crawl_url

        def mock_discover(html, source_url, base_domain, depth):
            return [
                _make_discovered_url("https://example.com/about", depth=depth),
                _make_discovered_url("https://example.com/contact", depth=depth),
            ]

        service._discover_links_from_html = mock_discover

        results = await service.crawl_site(
            "https://example.com", max_pages=10, max_depth=2
        )

        urls = [r["url"] for r in results]
        # Start page + about + contact = 3 (start URL not re-crawled)
        assert len(results) == 3
        assert len(urls) == len(set(urls))

    @pytest.mark.asyncio
    async def test_dedup_from_sitemap_and_bfs(self):
        """URLs discovered both via sitemap and BFS are only crawled once."""
        service = _make_service()

        service._discover_sitemap_urls = AsyncMock(
            return_value=["https://example.com/about"]
        )

        async def mock_crawl_url(url, **kwargs):
            html = '<html><body><a href="/about">About</a></body></html>'
            return _make_crawl_result(url, html=html)

        service.crawl_url = mock_crawl_url

        def mock_discover(html, source_url, base_domain, depth):
            return [_make_discovered_url("https://example.com/about", depth=depth)]

        service._discover_links_from_html = mock_discover

        results = await service.crawl_site(
            "https://example.com", max_pages=10, max_depth=2
        )

        urls = [r["url"] for r in results]
        # Start page (from BFS seed) + about (from sitemap) = 2
        # /about from BFS link discovery is deduped
        assert len(results) == 2
        assert len(urls) == len(set(urls))


class TestCrawlSiteEdgeCases:
    """Edge cases."""

    @pytest.mark.asyncio
    async def test_invalid_url_raises(self):
        """Invalid URL raises ValueError."""
        service = _make_service()
        with pytest.raises(ValueError):
            await service.crawl_site("not-a-url", max_pages=10, max_depth=2)

    @pytest.mark.asyncio
    async def test_empty_sitemap_falls_back_to_seed(self):
        """Empty sitemap discovery falls back to crawling the start URL."""
        service = _make_service()

        service._discover_sitemap_urls = AsyncMock(return_value=[])

        async def mock_crawl_url(url, **kwargs):
            return _make_crawl_result(url, html="<html></html>")

        service.crawl_url = mock_crawl_url
        service._discover_links_from_html = MagicMock(return_value=[])

        results = await service.crawl_site(
            "https://example.com", max_pages=10, max_depth=2
        )

        assert len(results) == 1
        assert results[0]["url"] == "https://example.com/"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
