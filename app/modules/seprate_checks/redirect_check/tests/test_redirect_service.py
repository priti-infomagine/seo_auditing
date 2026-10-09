"""Tests for RedirectCheckService URL discovery and domain normalization."""
import pytest

from app.modules.seprate_checks.redirect_check.service import RedirectCheckService


def test_normalize_domain_strips_path_and_returns_canonical():
    canonical, domain = RedirectCheckService._normalize_domain("example.com")
    assert domain == "example.com"
    assert canonical == "https://example.com"


def test_normalize_domain_preserves_https():
    canonical, domain = RedirectCheckService._normalize_domain("https://example.com")
    assert domain == "example.com"
    assert canonical == "https://example.com"


def test_normalize_domain_rejects_empty():
    with pytest.raises(ValueError):
        RedirectCheckService._normalize_domain("")


def test_normalize_domain_rejects_invalid():
    with pytest.raises(ValueError):
        RedirectCheckService._normalize_domain("not_a_domain")


def test_normalize_domain_handles_www():
    _canonical, domain = RedirectCheckService._normalize_domain("https://www.example.com")
    assert domain == "example.com"


def test_normalize_domain_handles_path():
    canonical, domain = RedirectCheckService._normalize_domain("example.com/some/path")
    assert domain == "example.com"
    assert canonical == "https://example.com"


def test_normalize_domain_handles_http():
    canonical, domain = RedirectCheckService._normalize_domain("http://example.com")
    assert domain == "example.com"
    assert canonical == "http://example.com"


@pytest.fixture
def mock_site_result():
    """Mock SiteDiscoveryResult for testing discover_urls."""
    from app.modules.crawler.services.site_discovery_service import (
        RobotsTxtEvidence,
        SiteDiscoveryResult,
        SitemapEvidence,
    )
    return SiteDiscoveryResult(
        robots=RobotsTxtEvidence(
            url="https://example.com/robots.txt",
            exists=True,
            status_code=200,
            content="User-agent: *\nDisallow: /admin/\nSitemap: https://example.com/sitemap.xml\n",
            rules_count=1,
            allows_crawling=True,
            sitemap_references=["https://example.com/sitemap.xml"],
        ),
        sitemaps=[
            SitemapEvidence(
                url="https://example.com/sitemap.xml",
                exists=True,
                status_code=200,
                content_type="application/xml",
                content_length=500,
                raw_content="<urlset></urlset>",
                urls=[
                    "https://example.com/",
                    "https://example.com/about",
                    "https://example.com/contact",
                ],
                child_sitemaps=[],
                is_index=False,
                error=None,
            ),
        ],
        discovered_urls=[],
        sitemap_probes=[],
    )


def test_build_sitemap_url_set_extracts_urls(mock_site_result):
    service = RedirectCheckService()
    url_set = service._build_sitemap_url_set(mock_site_result)
    assert "https://example.com/" in url_set
    assert "https://example.com/about" in url_set
    assert "https://example.com/contact" in url_set
