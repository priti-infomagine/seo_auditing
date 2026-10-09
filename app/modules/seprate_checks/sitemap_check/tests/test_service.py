import uuid
import pytest

from app.core.config import settings
from app.modules.crawler.services.site_discovery_service import (
    RobotsTxtEvidence,
    SiteDiscoveryResult,
    SitemapEvidence,
)
from app.modules.seprate_checks.sitemap_check.model import (
    SitemapCheck,
    SitemapCheckStatus,
    SitemapOverallStatus,
)
from app.modules.seprate_checks.sitemap_check.repository import SitemapCheckRepository
from app.modules.seprate_checks.sitemap_check.service import SitemapCheckService
from app.modules.seprate_checks.google_lighthouse_check.pagespeed_client import (
    PagespeedClient,
)


@pytest.fixture
def _set_api_key(monkeypatch):
    """Set a non-empty key to verify sitemap checks do not invoke PageSpeed."""
    monkeypatch.setattr(settings, "GOOGLE_PAGESPEED_API_KEY", "fake-api-key")
    yield


def _make_site_discovery_result():
    """Build a standard SiteDiscoveryResult used across service tests."""
    return SiteDiscoveryResult(
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
        sitemap_probes=[
            SitemapEvidence(
                url="https://example.com/sitemap.xml",
                exists=True,
                status_code=200,
                content_type="application/xml",
                urls=["https://example.com/", "https://example.com/about"],
            ),
            SitemapEvidence(
                url="https://example.com/sitemap_index.xml",
                exists=False,
                status_code=404,
                content_type="text/html; charset=utf-8",
            ),
        ],
    )


class FakeDiscovery:
    def __init__(self, *args, **kwargs):
        pass

    async def discover(self):
        return _make_site_discovery_result()


@pytest.mark.asyncio
async def test_prepare_check_persists_queued_record(db_session):
    """prepare_check validates URL and creates a QUEUED SitemapCheck."""
    check = await SitemapCheckService.prepare_check(
        "https://sub.example.com/some/path", db_session
    )
    assert check.id is not None
    assert check.status == SitemapCheckStatus.QUEUED
    assert check.domain == "sub.example.com"
    assert check.url == "https://sub.example.com"


@pytest.mark.asyncio
async def test_sitemap_check_async_success(monkeypatch, db_session):
    """run_check_async discovers sitemaps, evaluates rules, and marks COMPLETED."""
    check_id = uuid.uuid4()
    check = SitemapCheck(
        id=check_id,
        url="https://example.com",
        domain="example.com",
        status=SitemapCheckStatus.QUEUED,
    )
    db_session.add(check)
    await db_session.commit()

    monkeypatch.setattr(
        "app.modules.seprate_checks.sitemap_check.service.SiteDiscoveryService",
        FakeDiscovery,
    )

    summary_res = await SitemapCheckService().run_check_async(
        check_id=check_id, url="https://example.com", db=db_session
    )

    assert summary_res["status"] == "completed"
    assert summary_res["total_sitemaps"] == 2
    assert summary_res["total_urls"] == 3

    # Check DB row
    saved = await SitemapCheckRepository(db_session).get(check_id)
    assert saved.status == SitemapCheckStatus.COMPLETED
    assert saved.overall_status == SitemapOverallStatus.PASS
    assert saved.summary["total_sitemaps"] == 2
    assert len(saved.sitemaps) == 2
    assert any(
        probe["url"] == "https://example.com/sitemap_index.xml"
        and probe["status_code"] == 404
        for probe in saved.sitemap_results
    )
    assert saved.cost_seconds is not None
    assert "# Sitemap Audit Report" in saved.report_markdown
    assert (
        "- https://example.com/sitemap.xml | HTTP 200 | URLset | 2 entries"
        in saved.report_markdown
    )


@pytest.mark.asyncio
async def test_sitemap_check_async_reports_missing_sitemap(monkeypatch, db_session):
    """When no sitemaps exist, overall status is marked FAIL with recommendations."""
    check_id = uuid.uuid4()
    check = SitemapCheck(
        id=check_id,
        url="https://example.com",
        domain="example.com",
        status=SitemapCheckStatus.QUEUED,
    )
    db_session.add(check)
    await db_session.commit()

    result = SiteDiscoveryResult(
        robots=RobotsTxtEvidence(
            url="https://example.com/robots.txt",
            exists=True,
            status_code=200,
            sitemap_references=[],
        ),
        sitemaps=[],
        discovered_urls=[],
    )

    class FakeDiscoveryNoSitemaps:
        def __init__(self, *args, **kwargs):
            pass

        async def discover(self):
            return result

    monkeypatch.setattr(
        "app.modules.seprate_checks.sitemap_check.service.SiteDiscoveryService",
        FakeDiscoveryNoSitemaps,
    )

    summary_res = await SitemapCheckService().run_check_async(
        check_id=check_id, url="https://example.com", db=db_session
    )

    assert summary_res["status"] == "completed"
    assert summary_res["overall_status"] == "fail"

    saved = await SitemapCheckRepository(db_session).get(check_id)
    assert saved.status == SitemapCheckStatus.COMPLETED
    assert saved.overall_status == SitemapOverallStatus.FAIL
    finding_codes = {f["code"] for f in saved.findings}
    assert "sitemap_none_found" in finding_codes
    assert len(saved.recommendations) > 0


@pytest.mark.asyncio
async def test_sitemap_check_async_does_not_call_pagespeed(
    monkeypatch, db_session, _set_api_key
):
    """Sitemap checks never construct a PageSpeed client, even with an API key."""
    check_id = uuid.uuid4()
    check = SitemapCheck(
        id=check_id,
        url="https://example.com",
        domain="example.com",
        status=SitemapCheckStatus.QUEUED,
    )
    db_session.add(check)
    await db_session.commit()

    monkeypatch.setattr(
        "app.modules.seprate_checks.sitemap_check.service.SiteDiscoveryService",
        FakeDiscovery,
    )
    def fail_if_constructed(*args, **kwargs):
        pytest.fail("Sitemap checks must not construct a PageSpeed client")

    monkeypatch.setattr(PagespeedClient, "__init__", fail_if_constructed)

    summary_res = await SitemapCheckService().run_check_async(
        check_id=check_id, url="https://example.com", db=db_session
    )

    assert summary_res["status"] == "completed"

    saved = await SitemapCheckRepository(db_session).get(check_id)
    assert saved.status == SitemapCheckStatus.COMPLETED
    assert saved.accessibility_score is None
    assert saved.best_practices_score is None
    assert saved.summary["lighthouse_scored_pages"] == 0
    assert "Page-Level Lighthouse Scores" not in saved.report_markdown


def test_sitemap_index_entry_count_uses_child_sitemap_count():
    sitemap = SitemapEvidence(
        url="https://example.com/sitemap_index.xml",
        exists=True,
        status_code=200,
        content_type="application/xml",
        child_sitemaps=[
            "https://example.com/posts.xml",
            "https://example.com/pages.xml",
            "https://example.com/products.xml",
        ],
        is_index=True,
    )

    result = SitemapCheckService()._evaluate_sitemap_file(sitemap, "example.com")

    assert result.entry_count == 3
