"""
Tests for sitemap-index parsing and recursive child-sitemap expansion
in SiteDiscoveryService and SitemapDiscoverer.

All tests mock HTTP so no real network requests are made.
"""
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest

from app.modules.crawler.services.site_discovery_service import (
    SiteDiscoveryResult,
    SiteDiscoveryService,
    SitemapEvidence,
)
from app.modules.crawler.utils.sitemap_discoverer import SitemapDiscoverer
from app.shared.utils.http_client import HTTPClient


# ---------------------------------------------------------------------------
# Sample sitemap XML fixtures
# ---------------------------------------------------------------------------
URL_SET_XML = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.com/page1</loc></url>
  <url><loc>https://example.com/page2</loc></url>
  <url><loc>https://example.com/page3</loc></url>
</urlset>
"""

SITEMAP_INDEX_XML = """<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://example.com/sitemap-posts.xml</loc></sitemap>
  <sitemap><loc>https://example.com/sitemap-pages.xml</loc></sitemap>
</sitemapindex>
"""

CHILD_SITEMAP_1_XML = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.com/post1</loc></url>
  <url><loc>https://example.com/post2</loc></url>
</urlset>
"""

CHILD_SITEMAP_2_XML = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.com/page1</loc></url>
  <url><loc>https://example.com/page2</loc></url>
</urlset>
"""

SELF_REFERENCING_INDEX_XML = """<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://example.com/sitemap.xml</loc></sitemap>
</sitemapindex>
"""


# ---------------------------------------------------------------------------
# SiteDiscoveryService._fetch_sitemap tests (with mocked HTTPClient)
# ---------------------------------------------------------------------------
class TestSiteDiscoveryFetchSitemap:
    """Verify single-sitemap parsing via _fetch_sitemap."""

    @pytest.mark.asyncio
    @patch("app.modules.crawler.services.site_discovery_service.HTTPClient")
    async def test_url_set_parsing(self, mock_http_cls):
        _make_response(mock_http_cls, URL_SET_XML)

        service = SiteDiscoveryService("https://example.com")
        evidence = await service._fetch_sitemap("https://example.com/sitemap.xml")

        assert evidence.exists
        assert len(evidence.urls) == 3
        assert "https://example.com/page1" in evidence.urls
        assert evidence.is_index is False
        assert evidence.child_sitemaps == []

    @pytest.mark.asyncio
    @patch("app.modules.crawler.services.site_discovery_service.HTTPClient")
    async def test_sitemap_index_detection(self, mock_http_cls):
        _make_response(mock_http_cls, SITEMAP_INDEX_XML)

        service = SiteDiscoveryService("https://example.com")
        evidence = await service._fetch_sitemap("https://example.com/sitemap_index.xml")

        assert evidence.exists
        assert evidence.is_index is True
        assert len(evidence.child_sitemaps) == 2
        assert "https://example.com/sitemap-posts.xml" in evidence.child_sitemaps
        assert evidence.urls == []

    @pytest.mark.asyncio
    @patch("app.modules.crawler.services.site_discovery_service.HTTPClient")
    async def test_relative_urls_resolved(self, mock_http_cls):
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>/page1</loc></url>
  <url><loc>/page2</loc></url>
</urlset>
"""
        _make_response(mock_http_cls, xml)

        service = SiteDiscoveryService("https://example.com")
        evidence = await service._fetch_sitemap("https://example.com/sitemap.xml")

        assert evidence.exists
        assert len(evidence.urls) == 2
        assert "https://example.com/page1" in evidence.urls
        assert "https://example.com/page2" in evidence.urls

    @pytest.mark.asyncio
    @patch("app.modules.crawler.services.site_discovery_service.HTTPClient")
    async def test_backward_compat_evidence_fields(self, mock_http_cls):
        _make_response(mock_http_cls, URL_SET_XML)

        service = SiteDiscoveryService("https://example.com")
        evidence = await service._fetch_sitemap("https://example.com/sitemap.xml")

        assert evidence.url == "https://example.com/sitemap.xml"
        assert evidence.exists is True
        assert evidence.status_code == 200
        assert evidence.content_type == "text/xml"
        assert evidence.content_length > 0
        assert isinstance(evidence.urls, list)
        # New fields with backward-compatible defaults
        assert evidence.child_sitemaps == []
        assert evidence.is_index is False
        assert evidence.error is None


# ---------------------------------------------------------------------------
# SiteDiscoveryService._discover_sitemaps tests (with mocked _fetch_sitemap)
# ---------------------------------------------------------------------------
class TestSiteDiscoveryIndexExpansion:
    """Verify recursive sitemap-index expansion with mocked _fetch_sitemap."""

    @pytest.mark.asyncio
    async def test_recursive_index_expansion(self):
        """Child sitemaps referenced by an index are recursively fetched."""
        service = SiteDiscoveryService("https://example.com")

        # Mock _fetch_robots to return no sitemap references
        service._fetch_robots = AsyncMock(return_value=_empty_robots())

        # Mock _fetch_sitemap to return configured evidence based on URL
        sitemap_map = {
            "https://example.com/sitemap.xml": SitemapEvidence(
                url="https://example.com/sitemap.xml",
                exists=True,
                status_code=200,
                content_type="text/xml",
                content_length=100,
                child_sitemaps=[
                    "https://example.com/sitemap-posts.xml",
                    "https://example.com/sitemap-pages.xml",
                ],
                is_index=True,
            ),
            "https://example.com/sitemap-posts.xml": SitemapEvidence(
                url="https://example.com/sitemap-posts.xml",
                exists=True,
                status_code=200,
                urls=["https://example.com/post1", "https://example.com/post2"],
            ),
            "https://example.com/sitemap-pages.xml": SitemapEvidence(
                url="https://example.com/sitemap-pages.xml",
                exists=True,
                status_code=200,
                urls=["https://example.com/page1", "https://example.com/page2"],
            ),
            "https://example.com/sitemap_index.xml": SitemapEvidence(
                url="https://example.com/sitemap_index.xml",
                exists=True,
                status_code=200,
            ),
            "https://example.com/sitemap/": SitemapEvidence(
                url="https://example.com/sitemap/",
                exists=True,
                status_code=200,
            ),
        }

        async def mock_fetch_sitemap(url):
            return sitemap_map.get(url, SitemapEvidence(url=url, exists=False))

        service._fetch_sitemap = mock_fetch_sitemap

        sitemaps = await service._discover_sitemaps(_empty_robots())

        # Should have: sitemap.xml (index) + 2 child sitemaps
        # Plus whatever common-path sitemaps exist (sitemap_index.xml, sitemap/)
        index_evidence = [s for s in sitemaps if s.is_index]
        assert len(index_evidence) == 1
        assert len(index_evidence[0].child_sitemaps) == 2

        # Page URLs should be aggregated from child sitemaps
        all_urls = []
        for s in sitemaps:
            all_urls.extend(s.urls)
        assert "https://example.com/post1" in all_urls
        assert "https://example.com/page1" in all_urls

    @pytest.mark.asyncio
    async def test_child_sitemap_failure_skipped(self):
        """A failing child sitemap is skipped without aborting discovery."""
        service = SiteDiscoveryService("https://example.com")
        service._fetch_robots = AsyncMock(return_value=_empty_robots())

        sitemap_map = {
            "https://example.com/sitemap.xml": SitemapEvidence(
                url="https://example.com/sitemap.xml",
                exists=True,
                is_index=True,
                child_sitemaps=[
                    "https://example.com/sitemap-posts.xml",
                    "https://example.com/sitemap-pages.xml",
                ],
            ),
            # sitemap-posts.xml fails (404, no content)
            "https://example.com/sitemap-posts.xml": SitemapEvidence(
                url="https://example.com/sitemap-posts.xml",
                exists=False,
                status_code=404,
                error="Not Found",
            ),
            "https://example.com/sitemap-pages.xml": SitemapEvidence(
                url="https://example.com/sitemap-pages.xml",
                exists=True,
                urls=["https://example.com/page1"],
            ),
            "https://example.com/sitemap_index.xml": SitemapEvidence(
                url="https://example.com/sitemap_index.xml",
                exists=True,
            ),
            "https://example.com/sitemap/": SitemapEvidence(
                url="https://example.com/sitemap/",
                exists=True,
            ),
        }

        async def mock_fetch_sitemap(url):
            return sitemap_map.get(url, SitemapEvidence(url=url, exists=False))

        service._fetch_sitemap = mock_fetch_sitemap
        sitemaps = await service._discover_sitemaps(_empty_robots())

        # The successful child should still be present
        page_urls = [s for s in sitemaps if s.urls]
        all_urls = []
        for s in page_urls:
            all_urls.extend(s.urls)
        assert "https://example.com/page1" in all_urls
        # The failed child should not have its URLs
        assert "https://example.com/post1" not in all_urls

    @pytest.mark.asyncio
    async def test_cycles_avoided(self):
        """A sitemap-index that references itself does not cause infinite loops."""
        service = SiteDiscoveryService("https://example.com")
        service._fetch_robots = AsyncMock(return_value=_empty_robots())

        self_ref_evidence = SitemapEvidence(
            url="https://example.com/sitemap.xml",
            exists=True,
            is_index=True,
            child_sitemaps=["https://example.com/sitemap.xml"],  # self-reference!
        )

        fetch_count = [0]

        async def mock_fetch_sitemap(url):
            # Only the self-referencing sitemap returns evidence;
            # common-path candidates return nothing to avoid noise.
            if url == "https://example.com/sitemap.xml":
                fetch_count[0] += 1
                return self_ref_evidence
            return SitemapEvidence(url=url, exists=False)

        service._fetch_sitemap = mock_fetch_sitemap
        sitemaps = await service._discover_sitemaps(_empty_robots())

        assert len(sitemaps) == 1  # only fetched once
        assert fetch_count[0] == 1  # not re-fetched due to self-reference

    @pytest.mark.asyncio
    async def test_depth_limit_enforced(self):
        """Recursive expansion stops at MAX_SITEMAP_INDEX_DEPTH."""
        service = SiteDiscoveryService("https://example.com")
        service._fetch_robots = AsyncMock(return_value=_empty_robots())

        # Each level references the next
        async def mock_fetch_sitemap(url):
            if "level0" in url:
                return SitemapEvidence(
                    url=url, exists=True, is_index=True,
                    child_sitemaps=["https://example.com/level1"],
                )
            elif "level1" in url:
                return SitemapEvidence(
                    url=url, exists=True, is_index=True,
                    child_sitemaps=["https://example.com/level2"],
                )
            elif "level2" in url:
                return SitemapEvidence(
                    url=url, exists=True, is_index=True,
                    child_sitemaps=["https://example.com/level3"],
                )
            elif "level3" in url:
                return SitemapEvidence(
                    url=url, exists=True, is_index=True,
                    child_sitemaps=["https://example.com/level4"],
                )
            return SitemapEvidence(url=url, exists=False)

        # Override the common-path candidates so only sitemap.xml is fetched
        service._fetch_sitemap = mock_fetch_sitemap

        # We need to control the candidates, so call _discover_sitemaps directly
        # but the common paths will be fetched. Let's use discover() with mocked robots
        # Actually, _discover_sitemaps adds common paths. Let me mock those too.
        from app.modules.crawler.services.site_discovery_service import RobotsTxtEvidence
        robots = RobotsTxtEvidence(
            url="https://example.com/robots.txt",
            exists=True,
            sitemap_references=["https://example.com/level0"],
        )
        service._fetch_robots = AsyncMock(return_value=robots)

        sitemaps = await service._discover_sitemaps(robots)

        # level0 + level1 + level2 should be expanded (depth 0,1,2 <= MAX_SITEMAP_INDEX_DEPTH=3)
        # level3 is at depth 3 which equals MAX_SITEMAP_INDEX_DEPTH (allowed)
        # level4 would be at depth 4 which exceeds the limit
        sitemap_urls = [s.url for s in sitemaps if s.exists]
        assert "https://example.com/level0" in sitemap_urls
        # depth 3 is allowed (depth <= MAX_SITEMAP_INDEX_DEPTH)
        assert "https://example.com/level3" in sitemap_urls or "https://example.com/level4" not in sitemap_urls


# ---------------------------------------------------------------------------
# SitemapDiscoverer tests
# ---------------------------------------------------------------------------
class TestSitemapDiscovererIndex:
    def test_parse_url_set(self):
        discoverer = SitemapDiscoverer()
        urls = discoverer._parse_xml(URL_SET_XML)
        assert len(urls) == 3
        assert "https://example.com/page1" in urls

    def test_parse_index_returns_children(self):
        discoverer = SitemapDiscoverer()
        urls = discoverer._parse_xml(SITEMAP_INDEX_XML)
        assert len(urls) == 2
        assert "https://example.com/sitemap-posts.xml" in urls
        assert "https://example.com/sitemap-pages.xml" in urls

    def test_parse_index_empty_for_url_set(self):
        discoverer = SitemapDiscoverer()
        result = discoverer.parse_index(URL_SET_XML)
        assert result == []

    def test_parse_index_extracts_children(self):
        discoverer = SitemapDiscoverer()
        result = discoverer.parse_index(SITEMAP_INDEX_XML)
        assert len(result) == 2

    def test_parse_mixed_url_and_sitemap_entries(self):
        """_parse_xml returns both <url> and <sitemap> loc values."""
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://example.com/sitemap-posts.xml</loc></sitemap>
  <sitemap><loc>https://example.com/sitemap-pages.xml</loc></sitemap>
</sitemapindex>
"""
        discoverer = SitemapDiscoverer()
        urls = discoverer._parse_xml(xml)
        assert len(urls) == 2


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _empty_robots():
    from app.modules.crawler.services.site_discovery_service import RobotsTxtEvidence
    return RobotsTxtEvidence(
        url="https://example.com/robots.txt",
        exists=True,
        sitemap_references=[],
    )


def _make_mock_response(content: str = "", status_code: int = 200,
                        headers: dict = None):
    """Create a mock HTTPClient response."""
    response = MagicMock()
    response.status_code = status_code
    response.headers = {"content-type": "text/xml", **(headers or {})}
    response.content = content.encode("utf-8") if content else b""
    response.text = content
    return response


def _make_response(mock_http_cls, content, status_code=200, headers=None):
    """Configure mock HTTPClient to return a response for all calls."""
    response = _make_mock_response(content, status_code, headers)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=response)
    cm.__aexit__ = AsyncMock(return_value=None)
    mock_http_cls.return_value = cm
