import pytest

from app.modules.crawler.services.site_discovery_service import (
    RobotsTxtEvidence,
    SitemapEvidence,
    SiteDiscoveryResult,
)
from app.modules.seprate_checks.sitemap_check.service import SitemapCheckService


@pytest.mark.asyncio
async def test_sitemap_check_returns_all_content_and_recommendations(monkeypatch):
    result = SiteDiscoveryResult(
        robots=RobotsTxtEvidence(
            url="https://example.com/robots.txt",
            exists=True,
            status_code=200,
            sitemap_references=["https://example.com/sitemap.xml"],
        ),
        sitemaps=[
            SitemapEvidence(
                url="https://example.com/sitemap.xml",
                exists=True,
                status_code=200,
                content_type="application/xml",
                content_length=120,
                urls=["https://example.com/", "https://example.com/about"],
                raw_content="<urlset><url><loc>https://example.com/</loc></url></urlset>",
            ),
            SitemapEvidence(
                url="https://example.com/sitemap-blog.xml",
                exists=True,
                status_code=200,
                content_type="application/xml",
                content_length=90,
                urls=["https://example.com/blog"],
                raw_content="<urlset><url><loc>https://example.com/blog</loc></url></urlset>",
            ),
        ],
        discovered_urls=[
            "https://example.com/",
            "https://example.com/about",
            "https://example.com/blog",
        ],
    )

    class FakeDiscovery:
        def __init__(self, *args, **kwargs):
            pass

        async def discover(self):
            return result

    monkeypatch.setattr(
        "app.modules.seprate_checks.sitemap_check.service.SiteDiscoveryService",
        FakeDiscovery,
    )

    response = await SitemapCheckService().run_check("https://example.com")

    assert response.total_sitemap_files == 2
    assert response.total_page_urls == 3
    assert response.sitemap_files[0].raw_content.startswith("<urlset>")
    assert response.overall_status == "pass"
    assert "### Sitemap files" in response.report_markdown
    assert "### Recommendations and evidence" in response.report_markdown


@pytest.mark.asyncio
async def test_sitemap_check_reports_missing_sitemap(monkeypatch):
    result = SiteDiscoveryResult(
        robots=RobotsTxtEvidence(
            url="https://example.com/robots.txt",
            exists=True,
            status_code=200,
            sitemap_references=[],
        ),
    )

    class FakeDiscovery:
        def __init__(self, *args, **kwargs):
            pass

        async def discover(self):
            return result

    monkeypatch.setattr(
        "app.modules.seprate_checks.sitemap_check.service.SiteDiscoveryService",
        FakeDiscovery,
    )

    response = await SitemapCheckService().run_check("https://example.com")
    codes = {finding.code for finding in response.findings}

    assert response.overall_status == "fail"
    assert "sitemap_missing" in codes
    assert "Create an XML sitemap" in response.recommendations[0]
