"""Tests for the PageDiscoverer sitemap discovery and BFS logic."""
from __future__ import annotations

import pytest

from app.modules.category_check.core_seo.page_discoverer import PageDiscoverer


class MockHTTPClient:
    """Mock HTTP client that returns pre-canned responses keyed by URL."""

    def __init__(self, responses: dict[str, str] | None = None):
        self._responses = responses or {}

    async def fetch_text(self, url: str) -> str:
        # Strip query/fragment for lookup, return empty if not found
        return self._responses.get(url, "")

    async def fetch_html(self, url: str) -> str:
        return self._responses.get(url, "")


class TestParseSitemapXml:
    """Tests for _parse_sitemap_xml — page URLs vs child sitemap separation."""

    @pytest.mark.asyncio
    async def test_urlset_returns_page_urls_no_children(self):
        """A standard <urlset> sitemap returns page URLs and empty child_sitemaps."""
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.com/page1</loc></url>
  <url><loc>https://example.com/page2</loc></url>
</urlset>"""
        discoverer = PageDiscoverer(http_client=MockHTTPClient())
        page_urls, child_sitemaps = discoverer._parse_sitemap_xml(
            xml, "https://example.com/sitemap.xml", 100
        )
        assert len(page_urls) == 2
        assert page_urls[0] == "https://example.com/page1"
        assert page_urls[1] == "https://example.com/page2"
        assert child_sitemaps == []

    @pytest.mark.asyncio
    async def test_sitemapindex_returns_no_page_urls_but_children(self):
        """A <sitemapindex> returns child sitemap URLs and empty page_urls."""
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://example.com/sitemap-posts.xml</loc></sitemap>
  <sitemap><loc>https://example.com/sitemap-pages.xml</loc></sitemap>
</sitemapindex>"""
        discoverer = PageDiscoverer(http_client=MockHTTPClient())
        page_urls, child_sitemaps = discoverer._parse_sitemap_xml(
            xml, "https://example.com/sitemap_index.xml", 100
        )
        assert page_urls == []
        assert len(child_sitemaps) == 2
        assert "https://example.com/sitemap-posts.xml" in child_sitemaps
        assert "https://example.com/sitemap-pages.xml" in child_sitemaps

    @pytest.mark.asyncio
    async def test_deduplicates_page_urls(self):
        """Duplicate <loc> URLs in a urlset are deduplicated."""
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.com/page1</loc></url>
  <url><loc>https://example.com/page1</loc></url>
  <url><loc>https://example.com/page2</loc></url>
</urlset>"""
        discoverer = PageDiscoverer(http_client=MockHTTPClient())
        page_urls, _ = discoverer._parse_sitemap_xml(
            xml, "https://example.com/sitemap.xml", 100
        )
        assert len(page_urls) == 2


class TestDiscoverSitemapUrls:
    """Tests for _discover_sitemap_urls — robots.txt + common path probing."""

    @pytest.mark.asyncio
    async def test_finds_sitemap_at_common_path(self):
        """When robots.txt has no Sitemap: directive but /sitemap.xml exists,
        the discoverer still finds it via common-path probing."""
        responses = {
            "https://example.com/robots.txt": "# no sitemap here",
            "https://example.com/sitemap.xml": """<?xml version="1.0"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.com/page1</loc></url>
</urlset>""",
        }
        discoverer = PageDiscoverer(http_client=MockHTTPClient(responses))
        urls = await discoverer._discover_sitemap_urls(
            "https://example.com/", "example.com", 100
        )
        assert "https://example.com/page1" in urls

    @pytest.mark.asyncio
    async def test_finds_sitemap_from_robots_txt(self):
        """When robots.txt has a Sitemap: directive, the referenced sitemap is fetched."""
        responses = {
            "https://example.com/robots.txt": "Sitemap: https://example.com/sitemap.xml\n",
            "https://example.com/sitemap.xml": """<?xml version="1.0"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.com/page1</loc></url>
  <url><loc>https://example.com/page2</loc></url>
</urlset>""",
        }
        discoverer = PageDiscoverer(http_client=MockHTTPClient(responses))
        urls = await discoverer._discover_sitemap_urls(
            "https://example.com/", "example.com", 100
        )
        assert "https://example.com/page1" in urls
        assert "https://example.com/page2" in urls

    @pytest.mark.asyncio
    async def test_recursively_expands_sitemap_index(self):
        """A sitemap-index file is recursively expanded to fetch child sitemaps."""
        responses = {
            "https://example.com/robots.txt": "",
            "https://example.com/sitemap.xml": """<?xml version="1.0"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://example.com/sitemap-posts.xml</loc></sitemap>
</sitemapindex>""",
            "https://example.com/sitemap-posts.xml": """<?xml version="1.0"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.com/post/a</loc></url>
  <url><loc>https://example.com/post/b</loc></url>
</urlset>""",
        }
        discoverer = PageDiscoverer(http_client=MockHTTPClient(responses))
        urls = await discoverer._discover_sitemap_urls(
            "https://example.com/", "example.com", 100
        )
        assert "https://example.com/post/a" in urls
        assert "https://example.com/post/b" in urls

    @pytest.mark.asyncio
    async def test_no_sitemap_returns_empty(self):
        """When no sitemap is found anywhere, returns empty list."""
        responses = {
            "https://example.com/robots.txt": "# no sitemap here",
            "https://example.com/sitemap.xml": "",
            "https://example.com/wp-sitemap.xml": "",
        }
        discoverer = PageDiscoverer(http_client=MockHTTPClient(responses))
        urls = await discoverer._discover_sitemap_urls(
            "https://example.com/", "example.com", 100
        )
        assert urls == []


class TestDiscoverPages:
    """Tests for the public discover_pages method."""

    @pytest.mark.asyncio
    async def test_sitemap_urls_tagged_with_source_type_sitemap(self):
        """URLs discovered from sitemaps are tagged source_type='sitemap'."""
        xml = """<?xml version="1.0"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.com/page1</loc></url>
  <url><loc>https://example.com/page2</loc></url>
</urlset>"""
        responses = {
            "https://example.com/robots.txt": "Sitemap: https://example.com/sitemap.xml\n",
            "https://example.com/sitemap.xml": xml,
        }
        discoverer = PageDiscoverer(http_client=MockHTTPClient(responses))
        discovered = await discoverer.discover_pages(
            "https://example.com/", max_pages=100, max_depth=3
        )
        sitemap_discovered = [d for d in discovered if d.source_type == "sitemap"]
        assert len(sitemap_discovered) >= 2
        assert all(d.url in {"https://example.com/page1", "https://example.com/page2"} for d in sitemap_discovered)

    @pytest.mark.asyncio
    async def test_seed_url_always_present(self):
        """The start URL is always discovered as the seed."""
        responses = {
            "https://example.com/robots.txt": "",
        }
        discoverer = PageDiscoverer(http_client=MockHTTPClient(responses))
        discovered = await discoverer.discover_pages(
            "https://example.com/", max_pages=100, max_depth=3
        )
        seed_urls = [d for d in discovered if d.source_type == "seed"]
        assert len(seed_urls) == 1
        assert seed_urls[0].url == "https://example.com/"
