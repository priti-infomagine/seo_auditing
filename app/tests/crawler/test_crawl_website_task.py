"""
Tests for the ``crawler.crawl_website`` task's self-healing path.

When the worker picks up a Celery task but the ``CrawlJob`` row is
missing (e.g. the DB was reset between the POST /audit/analyze and
the worker picking up the task), the task must:

  1. NOT raise a ``ValueError`` (the historical behaviour).
  2. Recreate the ``CrawlJob`` row from the task arguments (crawl_id,
     url, user_id) with safe defaults.
  3. Continue so the orchestrator can run.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.modules.crawler.models.crawl_jobs import CrawlJob
from app.modules.crawler.repositories.crawl_job_repository import CrawlJobRepository
from app.modules.crawler.tasks import crawl_website as crawl_website_task


class _FakeSelf:
    """Minimal stand-in for the bound Celery task — exposes update_state()."""

    def __init__(self):
        self.states = []

    def update_state(self, state, meta=None):
        self.states.append({"state": state, "meta": meta})


@pytest.mark.asyncio
async def test_crawl_website_recreates_missing_crawljob_row(db_session):
    """When the CrawlJob row is missing, the task self-heals by INSERTing one."""
    fake_self = _FakeSelf()
    crawl_id = uuid4()
    user_id = uuid4()
    url = "https://radonindia.com/"

    class _Ctx:
        async def __aenter__(self_inner):
            return db_session

        async def __aexit__(self_inner, *exc):
            return False

    with patch("app.modules.crawler.tasks.async_session_factory") as factory:
        factory.side_effect = lambda: _Ctx()
        with patch("app.modules.crawler.tasks.CrawlOrchestrator") as orch_cls:
            orch_instance = orch_cls.return_value
            orch_instance.run = AsyncMock(return_value={"pages_crawled": 0})
            with patch("app.modules.crawler.tasks.celery_app") as fake_celery:
                fake_celery.send_task = lambda *a, **k: SimpleNamespace(id="t1")
                result = crawl_website_task.run(
                    fake_self, str(crawl_id), url, str(user_id)
                )

    assert result is not None
    assert result.get("pages_crawled") == 0

    count = (
        await db_session.execute(
            select(func.count()).select_from(CrawlJob).where(
                CrawlJob.id == crawl_id
            )
        )
    ).scalar_one()
    assert count == 1, "missing-row fallback did not recreate the CrawlJob"

    row = (
        await db_session.execute(select(CrawlJob).where(CrawlJob.id == crawl_id))
    ).scalar_one()
    assert row.url == url
    assert row.domain == "radonindia.com"
    assert row.user_id == user_id
    assert row.crawl_config is not None
    assert row.crawl_config.get("max_pages") == 100
    assert row.crawl_config.get("max_depth") == 5
    assert row.crawl_config.get("auto_analyze") is True


@pytest.mark.asyncio
async def test_crawl_website_skips_already_completed_job(db_session):
    """If the job exists but is already completed/failed/cancelled, the task
    returns early with the existing status — no recreate, no re-crawl."""
    crawl_id = uuid4()

    job = CrawlJob(
        id=crawl_id,
        user_id=uuid4(),
        url="https://example.com",
        domain="example.com",
        status="completed",
    )
    repo = CrawlJobRepository(db_session)
    await repo.create(job)
    await db_session.commit()

    class _Ctx:
        async def __aenter__(self_inner):
            return db_session

        async def __aexit__(self_inner, *exc):
            return False

    fake_self = _FakeSelf()
    with patch("app.modules.crawler.tasks.async_session_factory") as factory:
        factory.side_effect = lambda: _Ctx()
        with patch("app.modules.crawler.tasks.CrawlOrchestrator") as orch_cls:
            orch_instance = orch_cls.return_value
            orch_instance.run = AsyncMock(
                side_effect=AssertionError(
                    "orchestrator.run must not be called for a completed job"
                )
            )
            with patch("app.modules.crawler.tasks.celery_app") as fake_celery:
                fake_celery.send_task = lambda *a, **k: pytest.fail(
                    "celery_app.send_task must not be called for a completed job"
                )
                result = crawl_website_task.run(
                    fake_self, str(crawl_id), "https://example.com",
                    str(uuid4()),
                )

    assert result["status"] == "completed"
    assert result["crawl_id"] == str(crawl_id)


@pytest.mark.asyncio
async def test_crawl_website_runs_normally_when_row_exists(db_session):
    """The happy-path: row exists, status='queued', orchestrator runs,
    audit pipeline is fired."""
    crawl_id = uuid4()
    user_id = uuid4()

    job = CrawlJob(
        id=crawl_id,
        user_id=user_id,
        url="https://example.com",
        domain="example.com",
        status="queued",
        max_pages=10,
        max_depth=2,
        crawl_config={"max_pages": 10, "max_depth": 2, "auto_analyze": True},
    )
    repo = CrawlJobRepository(db_session)
    await repo.create(job)
    await db_session.commit()

    fired = []
    fake_self = _FakeSelf()

    class _Ctx:
        async def __aenter__(self_inner):
            return db_session

        async def __aexit__(self_inner, *exc):
            return False

    with patch("app.modules.crawler.tasks.async_session_factory") as factory:
        factory.side_effect = lambda: _Ctx()
        with patch("app.modules.crawler.tasks.CrawlOrchestrator") as orch_cls:
            orch_instance = orch_cls.return_value
            orch_instance.run = AsyncMock(return_value={"pages_crawled": 5})
            with patch("app.modules.crawler.tasks.celery_app") as fake_celery:
                def _capture(name, args=None, kwargs=None, queue=None, **opts):
                    fired.append({
                        "name": name, "args": args, "queue": queue,
                    })
                    return SimpleNamespace(id="t1")

                fake_celery.send_task = _capture
                result = crawl_website_task.run(
                    fake_self, str(crawl_id), "https://example.com",
                    str(user_id),
                )

    assert result["pages_crawled"] == 5
    assert result["auto_analyze"] is True
    assert any(
        f["name"] == "audit.run_analysis_pipeline" and f["queue"] == "audit"
        for f in fired
    ), f"audit pipeline not enqueued: {fired}"
