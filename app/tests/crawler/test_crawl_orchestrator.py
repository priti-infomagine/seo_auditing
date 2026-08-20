"""
Tests for the CrawlOrchestrator (app/modules/crawler/services/crawl_orchestrator.py).

Two layers are covered:

1. UNIT tests (fast, offline)
   The orchestrator's collaborators (job repository, persistence, scheduler) are
   replaced with lightweight fakes so lifecycle, progress, link-enqueue and the
   run() state machine can be verified without a database or network.

2. INTEGRATION / smoke test (live, opt-in)
   Runs the full `CrawlOrchestrator.run()` end-to-end against the real URL
   `https://vivo.com/`. Requires a reachable Postgres (see app/tests/conftest.py)
   and live network. Skipped by default; opt in with:

       RUN_LIVE_CRAWL=1 pytest app/tests/crawler/test_crawl_orchestrator.py -v -s

The supplied test URL is `https://vivo.com/`.
"""
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.modules.crawler.services.crawl_orchestrator import CrawlOrchestrator
from app.modules.crawler.types import DiscoveredURL

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeJob:
    """Minimal stand-in for the CrawlJob model used by the orchestrator."""

    def __init__(self):
        self.id = uuid4()
        self.crawl_config = {}
        self.status = "queued"
        self.total_pages = None
        self.current_page = None
        self.pages_crawled = 0
        self.pages_discovered = 0
        self.started_at = None
        self.completed_at = None
        self.duration_ms = None
        self.progress_percent = None
        self.error = None


class FakeJobRepository:
    def __init__(self, job=None):
        self.job = job
        self.updated = []

    async def get_by_id(self, crawl_job_id):
        return self.job

    async def update(self, job):
        self.updated.append(job)
        return job


class FakePersistence:
    def __init__(self):
        self.progress_updates = []
        self.site_data = []

    async def update_progress(self, current_page, total):
        self.progress_updates.append((current_page, total))

    async def persist_site_data(self, data):
        self.site_data.append(data)


class FakeScheduler:
    """Stand-in for CrawlScheduler used by the mocked run() tests."""

    def __init__(self, *args, **kwargs):
        self.pages_crawled_count = 3
        self.pages_discovered_count = 5
        self.seeds = []
        self.url_diagnostics = {}

    def submit_seed(self, url):
        self.seeds.append(url)
        return True

    def submit_sitemap_urls(self, urls, source_url=""):
        return len(urls)

    async def run(self):
        return None


class FakeSchedulerFail:
    """A scheduler whose run() raises, to exercise the failure path."""

    def __init__(self, *args, **kwargs):
        self.pages_crawled_count = 0
        self.pages_discovered_count = 0
        self.url_diagnostics = {}

    def submit_seed(self, url):
        return True

    def submit_sitemap_urls(self, urls, source_url=""):
        return len(urls)

    async def run(self):
        raise RuntimeError("scheduler exploded")


class RecordingScheduler:
    """Fake scheduler that records submit_discovered_url calls for _enqueue_links
    and tracks base_domain updates for redirect-aware tests."""

    def __init__(self, base_domain: str = ""):
        self.submitted = []
        self.base_domain = base_domain
        self.base_domain_updates = []

    def set_base_domain_from_url(self, url: str) -> None:
        from app.shared.utils.url_utils import normalize_host
        from urllib.parse import urlparse

        host = urlparse(url).hostname or ""
        self.base_domain_updates.append(url)
        self.base_domain = normalize_host(host)

    def submit_discovered_url(self, **kwargs):
        self.submitted.append(kwargs)
        return True

    @property
    def pages_crawled_count(self):
        return len(self.submitted)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_orchestrator(job=None):
    orch = CrawlOrchestrator(db=None, crawl_job_id=job.id if job else uuid4())
    orch.job_repository = FakeJobRepository(job)
    orch.persistence = FakePersistence()
    return orch


def make_enqueue_link(url, is_internal=True):
    return {"url": url, "is_internal": is_internal}

# ---------------------------------------------------------------------------
# Lifecycle / status helpers
# ---------------------------------------------------------------------------


class TestCrawlOrchestratorLifecycle:
    async def test_get_summary_returns_crawl_id(self):
        job = FakeJob()
        orch = make_orchestrator(job)
        summary = await orch.get_summary()
        assert summary["status"] == "completed"
        assert summary["crawl_id"] == str(job.id)

    async def test_set_status_crawling_sets_started_at_once(self):
        job = FakeJob()
        orch = make_orchestrator(job)

        await orch._set_status("crawling")
        assert job.status == "crawling"
        assert job.started_at is not None
        first_started = job.started_at

        # Running the status transition again must not clobber started_at.
        await orch._set_status("crawling")
        assert job.started_at == first_started

    async def test_mark_running_delegates_to_set_status(self):
        job = FakeJob()
        orch = make_orchestrator(job)
        await orch._mark_running()
        assert job.status == "crawling"

    async def test_finalize_status_sets_completion_fields(self):
        job = FakeJob()
        job.total_pages = 10
        orch = make_orchestrator(job)

        await orch._finalize_status("completed", duration_ms=1234)

        assert job.status == "completed"
        assert job.completed_at is not None
        assert job.duration_ms == 1234
        assert job.progress_percent == 100
        assert job.current_page == 10

    async def test_mark_completed_sets_completed(self):
        job = FakeJob()
        orch = make_orchestrator(job)
        await orch._mark_completed(999)
        assert job.status == "completed"
        assert job.duration_ms == 999

    async def test_mark_failed_sets_error_and_status(self):
        job = FakeJob()
        orch = make_orchestrator(job)
        await orch._mark_failed("boom")
        assert job.status == "failed"
        assert job.error == "boom"
        assert job.completed_at is not None
        assert job.progress_percent == 100

    async def test_mark_failed_truncates_long_error(self):
        job = FakeJob()
        orch = make_orchestrator(job)
        await orch._mark_failed("x" * 5000)
        assert len(job.error) <= 1024

    async def test_mark_failed_ignores_terminal_jobs(self):
        job = FakeJob()
        job.status = "completed"
        orch = make_orchestrator(job)
        await orch._mark_failed("should not apply")
        assert job.status == "completed"
        assert job.error is None


class TestCrawlOrchestratorProgress:
    async def test_update_progress_persists_and_notifies(self):
        job = FakeJob()
        job.total_pages = 100
        calls = []
        orch = make_orchestrator(job)
        orch.config = SimpleNamespace(max_pages=100)
        orch._progress_callback = lambda current, total: calls.append((current, total))

        await orch._update_progress(7)

        assert orch.persistence.progress_updates == [(7, 100)]
        assert calls == [(7, 100)]

    async def test_update_progress_survives_persistence_error(self):
        job = FakeJob()
        orch = make_orchestrator(job)
        orch.config = SimpleNamespace(max_pages=100)

        async def broken(*args, **kwargs):
            raise RuntimeError("db down")

        orch.persistence.update_progress = broken
        # Intended behaviour: orchestrator logs and continues, does not raise.
        await orch._update_progress(3)

# ---------------------------------------------------------------------------
# _enqueue_links link discovery fan-out
# ---------------------------------------------------------------------------


class TestCrawlOrchestratorEnqueueLinks:
    def _orchestrator_with_scheduler(self, max_depth=2):
        orch = make_orchestrator(FakeJob())
        orch.config = SimpleNamespace(max_depth=max_depth)
        recorded = RecordingScheduler()
        orch._scheduler = recorded
        return orch, recorded

    def test_submits_internal_links_within_depth(self):
        orch, recorded = self._orchestrator_with_scheduler(max_depth=2)
        links = [
            make_enqueue_link("https://vivo.com/phones"),
            make_enqueue_link("https://vivo.com/about"),
            make_enqueue_link("https://external.com", is_internal=False),
        ]
        orch._enqueue_links(
            links, page_id=uuid4(), page_url="https://vivo.com/", depth=0
        )

        assert len(recorded.submitted) == 2
        assert all(kw["depth"] == 1 for kw in recorded.submitted)
        assert all(kw["source_type"] == "html_link" for kw in recorded.submitted)
        assert all(kw["source_url"] == "https://vivo.com/" for kw in recorded.submitted)

    def test_skips_external_links(self):
        orch, recorded = self._orchestrator_with_scheduler()
        orch._enqueue_links(
            [make_enqueue_link("https://external.com", is_internal=False)],
            page_id=uuid4(),
            page_url="https://vivo.com/",
            depth=0,
        )
        assert recorded.submitted == []

    def test_respects_max_depth(self):
        orch, recorded = self._orchestrator_with_scheduler(max_depth=1)
        # depth=1 -> next_depth=2 > max_depth -> dropped
        orch._enqueue_links(
            [make_enqueue_link("https://vivo.com/child")],
            page_id=uuid4(),
            page_url="https://vivo.com/",
            depth=1,
        )
        assert recorded.submitted == []

    def test_max_depth_does_not_skip_remaining_links(self):
        orch, recorded = self._orchestrator_with_scheduler(max_depth=1)
        # With depth=0, next_depth=1 which is within max_depth=1.
        # Both internal links should be submitted.
        links = [
            {"url": "https://vivo.com/child-a", "is_internal": True},
            {"url": "https://vivo.com/child-b", "is_internal": True},
        ]
        orch._enqueue_links(
            links,
            page_id=uuid4(),
            page_url="https://vivo.com/",
            depth=0,
        )
        assert len(recorded.submitted) == 2
        assert all(kw["depth"] == 1 for kw in recorded.submitted)

    def test_strips_tracking_params_before_submit(self):
        orch, recorded = self._orchestrator_with_scheduler()
        orch._enqueue_links(
            [make_enqueue_link(
                "https://vivo.com/deal?utm_source=test&utm_medium=cpc&page=2"
            )],
            page_id=uuid4(),
            page_url="https://vivo.com/",
            depth=0,
        )
        assert len(recorded.submitted) == 1
        submitted_url = recorded.submitted[0]["url"]
        assert "utm_source" not in submitted_url
        assert "utm_medium" not in submitted_url
        assert "page=2" in submitted_url

    def test_noop_when_scheduler_missing(self):
        orch = make_orchestrator(FakeJob())
        orch.config = SimpleNamespace(max_depth=2)
        orch._scheduler = None
        # Must not raise.
        orch._enqueue_links(
            [make_enqueue_link("https://vivo.com/child")],
            page_id=uuid4(),
            page_url="https://vivo.com/",
            depth=0,
        )


# ---------------------------------------------------------------------------
# run()
# ---------------------------------------------------------------------------


class TestCrawlOrchestratorRun:
    async def test_run_success_marks_completed_and_records_counts(self, monkeypatch):
        job = FakeJob()
        orch = make_orchestrator(job)
        monkeypatch.setattr(
            "app.modules.crawler.services.crawl_orchestrator.CrawlScheduler",
            FakeScheduler,
        )

        result = await orch.run(start_url="https://vivo.com/", respect_robots=False)

        assert result["status"] == "completed"
        assert result["pages_crawled"] == 3
        assert result["pages_discovered"] == 5
        assert result["crawl_id"] == str(job.id)

        # Job was finalized and counts persisted.
        assert job.status == "completed"
        assert job.pages_crawled == 3
        assert job.pages_discovered == 5
        assert job.total_pages == 100  # default CrawlConfig.max_pages
        assert job in orch.job_repository.updated

    async def test_run_raises_when_job_missing(self, monkeypatch):
        orch = make_orchestrator(job=None)
        monkeypatch.setattr(
            "app.modules.crawler.services.crawl_orchestrator.CrawlScheduler",
            FakeScheduler,
        )
        with pytest.raises(ValueError):
            await orch.run(start_url="https://vivo.com/", respect_robots=False)

    async def test_run_marks_failed_when_scheduler_raises(self, monkeypatch):
        job = FakeJob()
        orch = make_orchestrator(job)
        monkeypatch.setattr(
            "app.modules.crawler.services.crawl_orchestrator.CrawlScheduler",
            FakeSchedulerFail,
        )

        result = await orch.run(start_url="https://vivo.com/", respect_robots=False)

        assert result["status"] == "failed"
        assert result["crawl_id"] == str(job.id)
        assert job.status == "failed"
        assert "scheduler exploded" in job.error

    async def test_run_attaches_robots_policy_to_scheduler(self, monkeypatch):
        job = FakeJob()
        orch = make_orchestrator(job)

        mock_scheduler_cls = MagicMock()
        mock_scheduler = MagicMock()
        mock_scheduler_cls.return_value = mock_scheduler
        monkeypatch.setattr(
            "app.modules.crawler.services.crawl_orchestrator.CrawlScheduler",
            mock_scheduler_cls,
        )

        mock_site_result = MagicMock()
        mock_site_result.robots.content = "User-agent: *\nAllow: /\n"
        mock_site_result.discovered_urls = []
        mock_site_result.sitemaps = []

        mock_discovery_instance = MagicMock()
        mock_discovery_instance.discover = AsyncMock(return_value=mock_site_result)
        monkeypatch.setattr(
            "app.modules.crawler.services.crawl_orchestrator.SiteDiscoveryService",
            lambda *a, **kw: mock_discovery_instance,
        )

        await orch.run(start_url="https://vivo.com/", respect_robots=True)

        assert mock_scheduler.set_robots_policy.called

    async def test_run_skips_robots_policy_when_no_content(self, monkeypatch):
        job = FakeJob()
        orch = make_orchestrator(job)

        mock_scheduler_cls = MagicMock()
        mock_scheduler = MagicMock()
        mock_scheduler_cls.return_value = mock_scheduler
        monkeypatch.setattr(
            "app.modules.crawler.services.crawl_orchestrator.CrawlScheduler",
            mock_scheduler_cls,
        )

        mock_site_result = MagicMock()
        mock_site_result.robots.content = None
        mock_site_result.discovered_urls = []
        mock_site_result.sitemaps = []

        mock_discovery_instance = MagicMock()
        mock_discovery_instance.discover = AsyncMock(return_value=mock_site_result)
        monkeypatch.setattr(
            "app.modules.crawler.services.crawl_orchestrator.SiteDiscoveryService",
            lambda *a, **kw: mock_discovery_instance,
        )

        await orch.run(start_url="https://vivo.com/", respect_robots=True)

        assert not mock_scheduler.set_robots_policy.called

# ---------------------------------------------------------------------------
# crawl_page backward-compat wrapper
# ---------------------------------------------------------------------------


class TestCrawlPageWrapper:
    async def test_crawl_page_delegates_to_crawl_page(self):
        import asyncio

        from unittest.mock import AsyncMock

        job = FakeJob()
        orch = make_orchestrator(job)
        orch.config = SimpleNamespace(http_concurrency=10, browser_concurrency=3)
        mocked = AsyncMock()
        orch._crawl_page = mocked

        await orch.crawl_page("https://vivo.com/phones", depth=2)

        assert mocked.await_count == 1
        item = mocked.await_args.args[0]
        assert isinstance(item, DiscoveredURL)
        assert item.url == "https://vivo.com/phones"
        assert item.depth == 2
        # Semaphores are passed as keyword arguments.
        kwargs = mocked.await_args.kwargs
        assert isinstance(kwargs["http_sem"], asyncio.Semaphore)
        assert isinstance(kwargs["browser_sem"], asyncio.Semaphore)

    async def test_crawl_page_uses_default_semaphores_without_config(self):
        import asyncio

        from unittest.mock import AsyncMock

        job = FakeJob()
        orch = make_orchestrator(job)
        orch.config = None
        mocked = AsyncMock()
        orch._crawl_page = mocked

        await orch.crawl_page("https://vivo.com/")

        assert mocked.await_count == 1
        kwargs = mocked.await_args.kwargs
        assert isinstance(kwargs["http_sem"], asyncio.Semaphore)
        assert isinstance(kwargs["browser_sem"], asyncio.Semaphore)


# ---------------------------------------------------------------------------
# Redirect-aware seed handling — _crawl_page
# ---------------------------------------------------------------------------


class TestCrawlPageRedirectAware:
    """Tests 8-10: verify that _crawl_page resolves links against the
    effective (post-redirect) URL and updates the scheduler base domain
    correctly for same-site vs external redirects."""

    def _make_orchestrator(self, base_domain="example.com"):
        from unittest.mock import AsyncMock, MagicMock
        from asyncio import Semaphore

        from app.modules.crawler.config import CrawlConfig
        from app.modules.crawler.types import FetchResult, RedirectInfo
        from app.modules.crawler.services.page_crawl_service import PageCrawlResult

        orch = make_orchestrator(FakeJob())
        orch.config = CrawlConfig.from_dict(
            {"max_pages": 10, "max_depth": 3, "respect_robots": False}
        )

        # Real parser + extraction (processes HTML we control)
        # page_extraction_service is already set by __init__
        # technical_analysis_service is real too — lightweight

        # Mock page_crawl_service.crawl_page — tests set return value via helper
        orch.page_crawl_service = MagicMock()

        # Mock persistence
        fake_page = MagicMock()
        fake_page.id = uuid4()
        mock_persist = AsyncMock(side_effect=lambda page: fake_page)
        orch.persistence.persist_page = mock_persist
        orch.persistence.persist_snapshot = AsyncMock()
        orch.persistence.persist_network_data = AsyncMock()
        orch.persistence.persist_seo_data = AsyncMock()
        orch.persistence.persist_resources = AsyncMock(return_value=[])
        orch.persistence.persist_links = AsyncMock(return_value=[])
        orch.persistence.update_progress = AsyncMock()
        orch.persistence.persist_error = AsyncMock()

        # Mock redirect service factory
        fake_redirect_service = MagicMock()
        fake_redirect_service.process_and_save_redirects = AsyncMock()
        orch.redirect_service_factory = MagicMock(return_value=fake_redirect_service)

        # Mock event bus
        orch.event_bus = MagicMock()
        orch.event_bus.emit = AsyncMock()

        # Recording scheduler with base_domain tracking
        recorded = RecordingScheduler(base_domain=base_domain)
        orch._scheduler = recorded

        return orch, recorded

    def _make_fetch_result(self, final_url, redirect_chain=None):
        """Build a FetchResult simulating what page_crawl_service returns."""
        from app.modules.crawler.types import FetchResult, RedirectInfo

        chain = redirect_chain or []
        if chain:
            status_code = chain[-1].status_code
        else:
            status_code = 200

        return FetchResult(
            url=final_url,
            normalized_url=final_url,
            status_code=status_code,
            content=b"",
            headers={},
            final_url=final_url,
            content_type="text/html",
            content_length=0,
            response_time_ms=0,
            redirect_chain=chain,
            success=True,
        )

    async def test_same_site_redirect_updates_base_domain(self):
        """Test 8: HTTP→HTTPS same-site redirect updates base_domain and
        resolves relative links against the effective (post-redirect) URL."""
        from app.modules.crawler.services.page_crawl_service import PageCrawlResult
        from app.modules.crawler.extractors.document_extractor import DocumentFacts
        from app.modules.crawler.types import RedirectInfo
        from unittest.mock import AsyncMock
        from asyncio import Semaphore

        orch, recorded = self._make_orchestrator(base_domain="example.com")

        html = '<html><body><a href="/about">About</a></body></html>'

        mock_result = PageCrawlResult(
            url="http://example.com/page",
            normalized_url="http://example.com/page",
            document=DocumentFacts(raw_html=html),
            fetch_result=self._make_fetch_result(
                "https://example.com/page",
                redirect_chain=[RedirectInfo(url="http://example.com/page", status_code=301, location="https://example.com/page")],
            ),
        )
        orch.page_crawl_service.crawl_page = AsyncMock(return_value=mock_result)

        item = DiscoveredURL(
            url="http://example.com/page",
            normalized_url="http://example.com/page",
            source_url="http://example.com/page",
            source_type="seed",
            depth=0,
        )
        await orch._crawl_page(item, http_sem=Semaphore(5), browser_sem=Semaphore(3))

        assert recorded.base_domain == "example.com"
        assert len(recorded.submitted) == 1
        submitted_url = recorded.submitted[0]["url"]
        assert submitted_url == "https://example.com/about"

    async def test_external_redirect_does_not_expand_scope(self):
        """Test 9: Redirect to an unrelated host does NOT change base_domain —
        relative links are still resolved against the effective (redirect) URL
        but the scheduler scope stays at the original site."""
        from app.modules.crawler.services.page_crawl_service import PageCrawlResult
        from app.modules.crawler.extractors.document_extractor import DocumentFacts
        from app.modules.crawler.types import RedirectInfo
        from unittest.mock import AsyncMock
        from asyncio import Semaphore

        orch, recorded = self._make_orchestrator(base_domain="example.com")

        html = '<html><body><a href="/about">About</a></body></html>'

        mock_result = PageCrawlResult(
            url="http://example.com/page",
            normalized_url="http://example.com/page",
            document=DocumentFacts(raw_html=html),
            fetch_result=self._make_fetch_result(
                "https://unrelated.com/page",
                redirect_chain=[
                    RedirectInfo(url="http://example.com/page", status_code=302, location="https://unrelated.com/page"),
                ],
            ),
        )
        orch.page_crawl_service.crawl_page = AsyncMock(return_value=mock_result)

        item = DiscoveredURL(
            url="http://example.com/page",
            normalized_url="http://example.com/page",
            source_url="http://example.com/page",
            source_type="seed",
            depth=0,
        )
        await orch._crawl_page(item, http_sem=Semaphore(5), browser_sem=Semaphore(3))

        # base_domain must NOT have changed to unrelated.com
        assert recorded.base_domain == "example.com"
        assert "unrelated.com" not in recorded.base_domain_updates

        # Relative link resolves against the effective (post-redirect) URL
        # because the parser was given effective_url as its base.
        assert len(recorded.submitted) == 1
        submitted_url = recorded.submitted[0]["url"]
        assert submitted_url == "https://unrelated.com/about"

    async def test_relative_link_resolution_against_effective_url(self):
        """Test 10: A redirect that changes the path (e.g. /old → /new) must
        cause relative links like ./products to resolve against the new path,
        not the original."""
        from app.modules.crawler.services.page_crawl_service import PageCrawlResult
        from app.modules.crawler.extractors.document_extractor import DocumentFacts
        from app.modules.crawler.types import RedirectInfo
        from unittest.mock import AsyncMock
        from asyncio import Semaphore

        orch, recorded = self._make_orchestrator(base_domain="example.com")

        html = '<html><body><a href="./products">Products</a></body></html>'

        mock_result = PageCrawlResult(
            url="http://example.com/old",
            normalized_url="http://example.com/old",
            document=DocumentFacts(raw_html=html),
            fetch_result=self._make_fetch_result(
                "https://example.com/new",
                redirect_chain=[
                    RedirectInfo(url="http://example.com/old", status_code=301, location="https://example.com/new"),
                ],
            ),
        )
        orch.page_crawl_service.crawl_page = AsyncMock(return_value=mock_result)

        item = DiscoveredURL(
            url="http://example.com/old",
            normalized_url="http://example.com/old",
            source_url="http://example.com/old",
            source_type="seed",
            depth=0,
        )
        await orch._crawl_page(item, http_sem=Semaphore(5), browser_sem=Semaphore(3))

        # ./products resolved against https://example.com/new =>
        # https://example.com/products (NOT https://example.com/newproducts)
        assert len(recorded.submitted) == 1
        submitted_url = recorded.submitted[0]["url"]
        assert submitted_url == "https://example.com/products"


# ---------------------------------------------------------------------------
# Live integration / smoke test against https://vivo.com/
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    os.environ.get("RUN_LIVE_CRAWL") != "1",
    reason="Opt-in live crawl. Set RUN_LIVE_CRAWL=1 to run against https://vivo.com/",
)
async def test_live_crawl_vivo_com(db_session):
    """Run the full orchestrator against https://vivo.com/ and verify persistence.

    Requires a reachable Postgres (app/tests/conftest.py provides db_session)
    and live network access. Opt in with RUN_LIVE_CRAWL=1.
    """
    from app.modules.crawler.models.crawl_jobs import CrawlJob
    from app.modules.crawler.repositories.crawl_job_repository import CrawlJobRepository
    from app.shared.utils.url_utils import get_domain

    start_url = "https://vivo.com/"
    domain = get_domain(start_url)

    job = CrawlJob(
        id=uuid4(),
        user_id=uuid4(),
        url=start_url,
        domain=domain,
        status="queued",
        crawl_config={
            "max_pages": 1,
            "max_depth": 0,
            "concurrency": 2,
            "request_timeout": 30.0,
            "respect_robots": False,
            "enable_browser_rendering": False,
            "render_fallback_enabled": False,
        },
    )
    repo = CrawlJobRepository(db_session)
    await repo.create(job)

    orchestrator = CrawlOrchestrator(db_session, job.id)
    result = await orchestrator.run(
        start_url=start_url,
        max_pages=1,
        max_depth=0,
        concurrency=2,
        respect_robots=False,
    )

    # The run always returns an orchestrator-shaped summary.
    assert "status" in result
    assert result["crawl_id"] == str(job.id)

    refreshed = await repo.get_by_id(job.id)
    assert refreshed is not None
    assert refreshed.pages_crawled >= 0
    assert refreshed.pages_discovered >= 0

    if result["status"] == "completed":
        assert refreshed.status == "completed"
        assert refreshed.pages_crawled >= 1
    else:
        # For a live, externally-controlled site the crawl may legitimately fail
        # (bot protection, geo-redirects, timeouts). Assert we still finalised.
        assert refreshed.status == "failed"
        assert refreshed.error is not None

