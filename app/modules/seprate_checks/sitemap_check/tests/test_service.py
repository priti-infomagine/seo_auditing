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


@pytest.fixture
def _empty_api_key(monkeypatch):
    """Ensure GOOGLE_PAGESPEED_API_KEY is empty for graceful-degradation tests."""
    monkeypatch.setattr(settings, "GOOGLE_PAGESPEED_API_KEY", "")
    yield


@pytest.fixture
def _set_api_key(monkeypatch):
    """Set a non-empty GOOGLE_PAGESPEED_API_KEY for tests that need PageSpeed."""
    monkeypatch.setattr(settings, "GOOGLE_PAGESPEED_API_KEY", "fake-api-key")
    yield


class FakePagespeedClient:
    """Mock PagespeedClient that returns deterministic scores."""

    def __init__(self, api_key=None):
        self.api_key = api_key

    async def fetch(self, url, strategy="mobile", category=None):
        return {
            "lighthouseResult": {
                "categories": {
                    "accessibility": {"score": 0.9},
                    "best-practices": {"score": 0.8},
                },
                "audits": {},
            }
        }

    async def close(self):
        pass

    @staticmethod
    def parse_result(raw, url, device):
        return {
            "url": url,
            "device": device,
            "performance_score": 85,
            "seo_score": 90,
            "accessibility_score": 90,
            "best_practices_score": 80,
            "fcp_ms": 1000,
            "lcp_ms": 2000,
            "tbt_ms": 300,
            "cls": 0.1,
            "recommendations": [],
        }


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
async def test_sitemap_check_async_with_pagespeed_scores(
    monkeypatch, db_session, _set_api_key
):
    """run_check_async calls PageSpeed and persists accessibility + best-practices scores."""
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
    monkeypatch.setattr(
        "app.modules.seprate_checks.sitemap_check.service.PagespeedClient",
        FakePagespeedClient,
    )

    summary_res = await SitemapCheckService().run_check_async(
        check_id=check_id, url="https://example.com", db=db_session
    )

    assert summary_res["status"] == "completed"

    saved = await SitemapCheckRepository(db_session).get(check_id)
    assert saved.status == SitemapCheckStatus.COMPLETED
    assert saved.accessibility_score is not None
    assert saved.best_practices_score is not None
    assert 0 <= saved.accessibility_score <= 100
    assert 0 <= saved.best_practices_score <= 100
    assert saved.summary["lighthouse_scored_pages"] > 0
    assert "Page-Level Lighthouse Scores" in saved.report_markdown
    assert (
        f"Accessibility Score (avg)" in saved.report_markdown
    )


@pytest.mark.asyncio
async def test_sitemap_check_async_degrades_without_api_key(
    monkeypatch, db_session, _empty_api_key
):
    """When GOOGLE_PAGESPEED_API_KEY is empty, sitemap check still succeeds with scores = None."""
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

    saved = await SitemapCheckRepository(db_session).get(check_id)
    assert saved.status == SitemapCheckStatus.COMPLETED
    assert saved.accessibility_score is None
    assert saved.best_practices_score is None
    assert saved.summary["lighthouse_scored_pages"] == 0

    # No lighthouse-related findings should be added when API key is missing
    finding_codes = {f["code"] for f in saved.findings}
    assert "lighthouse_scores_unavailable" not in finding_codes
    assert "lighthouse_api_key_missing" not in finding_codes

    # Overall status should still be PASS (no extra low findings)
    assert saved.overall_status == SitemapOverallStatus.PASS
