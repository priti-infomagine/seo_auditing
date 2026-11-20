import asyncio
import uuid

import pytest

from app.modules.separate_checks.meta_check.model import MetaCheck, MetaCheckStatus
from app.modules.separate_checks.meta_check.repository import MetaCheckRepository
from app.modules.separate_checks.meta_check.service import MetaCheckService
from app.modules.separate_checks.meta_check import service as service_module


@pytest.mark.asyncio
async def test_completed_check_does_not_run_crawler(db_session, monkeypatch):
    check = MetaCheck(
        id=uuid.uuid4(),
        url="https://example.com/",
        domain="example.com",
        status="completed",
        pages=[{"url": "https://example.com/"}],
        summary={"pages_checked": 1, "total_findings": 2},
        findings=[{}, {}],
    )
    db_session.add(check)
    await db_session.commit()

    def unexpected_crawler(*args, **kwargs):
        pytest.fail("A completed metadata check must not crawl again")

    monkeypatch.setattr(
        "app.modules.separate_checks.meta_check.service.CrawlOrchestrator",
        unexpected_crawler,
    )

    result = await MetaCheckService().run_check_async(check.id, db=db_session)

    assert result == {
        "status": "completed",
        "check_id": str(check.id),
        "pages_checked": 1,
        "total_findings": 2,
    }


@pytest.mark.asyncio
async def test_crawl_timeout_marks_check_failed(db_session, monkeypatch):
    check = MetaCheck(
        id=uuid.uuid4(),
        url="https://example.com/",
        domain="example.com",
        status="queued",
        progress={"respect_robots": False},
    )
    db_session.add(check)
    await db_session.commit()
    monkeypatch.setattr(service_module, "META_CHECK_CRAWL_TIMEOUT_SECONDS", 0.01)

    class StallingOrchestrator:
        def __init__(self, *args, **kwargs):
            pass

        async def run(self, **kwargs):
            await asyncio.Event().wait()

    monkeypatch.setattr(service_module, "CrawlOrchestrator", StallingOrchestrator)

    with pytest.raises(asyncio.TimeoutError):
        await MetaCheckService().run_check_async(check.id, db=db_session)

    await db_session.refresh(check)
    assert check.status == "failed"
    assert "Metadata crawl exceeded" in check.error


@pytest.mark.asyncio
async def test_processing_transition_clears_stale_error(db_session):
    check = MetaCheck(
        id=uuid.uuid4(),
        url="https://example.com/",
        domain="example.com",
        status="failed",
        error="Parser bug: soup not defined",
    )
    db_session.add(check)
    await db_session.commit()

    await MetaCheckRepository(db_session).update_progress(
        check.id,
        MetaCheckStatus.PROCESSING,
        progress={"phase": "crawling"},
    )
    await db_session.commit()
    await db_session.refresh(check)

    assert check.error is None
