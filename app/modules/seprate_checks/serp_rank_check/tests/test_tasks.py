"""Celery task tests for the SERP rank check module."""
from __future__ import annotations

import httpx
import pytest

from app.shared.tasks.celery_app import celery_app
from app.shared.tasks.celery_config import task_routes

from app.modules.seprate_checks.serp_rank_check.exceptions import (
    SerpProvider5xx,
)
from app.modules.seprate_checks.serp_rank_check.model import (
    RankCheckStatus,
)
from app.modules.seprate_checks.serp_rank_check.repository import (
    RankCheckRepository,
)
from app.modules.seprate_checks.serp_rank_check.service import (
    SerpRankCheckService,
)
from app.modules.seprate_checks.serp_rank_check.tasks import (
    build_preview,
    refresh_reference_data,
    run_serp_check,
    sweep_stuck_checks,
)

from .conftest import FAKE_USER_ID


def _force_task_retries(task, retries, monkeypatch):
    """Make the task's request context report *retries*."""
    original_push = task.push_request

    def patched_push(**kwargs):
        kwargs["retries"] = retries
        original_push(**kwargs)

    monkeypatch.setattr(task, "push_request", patched_push)


async def _create_check(db_session, **overrides):
    params = dict(
        user_id=FAKE_USER_ID,
        keyword="seo tools",
        domain="example.com",
        location_code=2840,
        language_code="en",
        device="desktop",
        depth=10,
        include_preview=False,
    )
    params.update(overrides)
    service = SerpRankCheckService(db_session)
    return await service.prepare_check(**params)


async def _reload(service_session_factory, check_id):
    """Read a check back through a fresh session.

    The task mutates state through its own session
    (``async_session_factory``), so the test's ``db_session``
    would return a stale copy. A fresh session always observes
    the committed state — mirroring how a worker process reads
    the row.
    """
    async with service_session_factory() as session:
        return await RankCheckRepository(session).get(check_id)


class TestTaskConfiguration:
    def test_run_serp_check_routing_and_limits(self):
        assert run_serp_check.queue == "serp_io"
        assert run_serp_check.max_retries == 3
        assert run_serp_check.acks_late is True
        assert run_serp_check.soft_time_limit == 45
        assert run_serp_check.time_limit == 60
        assert run_serp_check.track_started is True

    def test_run_serp_check_autoretries_only_provider_errors(self):
        from app.modules.seprate_checks.serp_rank_check.exceptions import (
            SerpProviderTimeout,
        )

        autoretry_for = run_serp_check.autoretry_for
        assert SerpProviderTimeout in autoretry_for
        assert SerpProvider5xx in autoretry_for
        assert len(autoretry_for) == 2

    def test_build_preview_routing(self):
        assert build_preview.queue == "serp_preview"
        assert build_preview.max_retries == 0
        assert build_preview.acks_late is True

    def test_maintenance_tasks_routing(self):
        assert sweep_stuck_checks.queue == "serp_maintenance"
        assert refresh_reference_data.queue == "serp_maintenance"

    def test_task_routes_map_queues(self):
        assert task_routes["serp_rank_check.run_serp_check"][
            "queue"
        ] == "serp_io"
        assert task_routes["serp_rank_check.build_preview"][
            "queue"
        ] == "serp_preview"
        assert task_routes["serp_rank_check.sweep_stuck_checks"][
            "queue"
        ] == "serp_maintenance"
        assert task_routes[
            "serp_rank_check.refresh_reference_data"
        ]["queue"] == "serp_maintenance"

    def test_beat_schedule_has_serp_jobs(self):
        schedule = celery_app.conf.beat_schedule
        assert "serp-sweep-stuck-checks" in schedule
        assert schedule["serp-sweep-stuck-checks"]["schedule"] == 300.0
        assert "serp-refresh-reference-data" in schedule
        assert (
            schedule["serp-refresh-reference-data"]["schedule"]
            == 604800.0
        )

    def test_serp_tasks_registered(self):
        assert "serp_rank_check.run_serp_check" in celery_app.tasks
        assert "serp_rank_check.build_preview" in celery_app.tasks
        assert (
            "serp_rank_check.sweep_stuck_checks"
            in celery_app.tasks
        )
        assert (
            "serp_rank_check.refresh_reference_data"
            in celery_app.tasks
        )


@pytest.mark.asyncio
async def test_run_serp_check_task_invokes_service(
    seed_reference,
    service_session_factory,
    sent_tasks,
    monkeypatch,
    db_session,
):
    captured = {}

    async def fake_run(self, check_id):
        captured["check_id"] = check_id
        return {"id": str(check_id), "status": "done"}

    monkeypatch.setattr(
        SerpRankCheckService, "run_check_async", fake_run
    )
    check, _ = await _create_check(db_session)
    result = run_serp_check(str(check.id))
    assert captured["check_id"] == check.id
    assert result["status"] == "done"


@pytest.mark.asyncio
async def test_run_serp_check_task_does_not_mark_failed(
    seed_reference,
    service_session_factory,
    fake_serp_client,
    db_session,
):
    # A direct call runs with retries=0 (< max_retries=3), so a
    # retryable failure must NOT mark the check failed — Celery
    # will redeliver it.
    fake_serp_client.set_response(
        exc=SerpProvider5xx("provider 5xx")
    )
    check, _ = await _create_check(db_session)
    with pytest.raises(SerpProvider5xx):
        run_serp_check(str(check.id))

    stored = await _reload(service_session_factory, check.id)
    assert stored.status == RankCheckStatus.RUNNING.value
    assert stored.error_code is None


@pytest.mark.asyncio
async def test_run_serp_check_task_marks_failed_on_final_attempt(
    seed_reference,
    service_session_factory,
    fake_serp_client,
    monkeypatch,
    db_session,
):
    fake_serp_client.set_response(
        exc=SerpProvider5xx("provider 5xx")
    )
    _force_task_retries(
        run_serp_check, run_serp_check.max_retries, monkeypatch
    )
    check, _ = await _create_check(db_session)
    with pytest.raises(SerpProvider5xx):
        run_serp_check(str(check.id))

    stored = await _reload(service_session_factory, check.id)
    assert stored.status == RankCheckStatus.FAILED.value
    assert stored.error_code == "PROVIDER_5XX"


@pytest.mark.asyncio
async def test_run_serp_check_task_marks_timeout_failed_on_final_attempt(
    seed_reference,
    service_session_factory,
    fake_serp_client,
    monkeypatch,
    db_session,
):
    fake_serp_client.set_response(
        exc=httpx.ReadTimeout("read timed out")
    )
    _force_task_retries(
        run_serp_check, run_serp_check.max_retries, monkeypatch
    )
    check, _ = await _create_check(db_session)
    with pytest.raises(Exception):
        run_serp_check(str(check.id))

    stored = await _reload(service_session_factory, check.id)
    assert stored.status == RankCheckStatus.FAILED.value
    assert stored.error_code == "PROVIDER_TIMEOUT"


@pytest.mark.asyncio
async def test_build_preview_task_invokes_service(
    seed_reference,
    service_session_factory,
    monkeypatch,
    db_session,
):
    captured = {}

    async def fake_build(self, check_id):
        captured["check_id"] = check_id
        return {
            "id": str(check_id),
            "status": "done",
            "preview_status": "done",
        }

    monkeypatch.setattr(
        SerpRankCheckService, "build_preview_async", fake_build
    )
    check, _ = await _create_check(db_session)
    result = build_preview(str(check.id))
    assert captured["check_id"] == check.id
    assert result["preview_status"] == "done"


@pytest.mark.asyncio
async def test_sweep_task_invokes_service(
    service_session_factory,
    monkeypatch,
):
    captured = {}

    async def fake_sweep(self):
        captured["called"] = True
        return {"swept": 0, "resumed": 0, "failed": 0}

    monkeypatch.setattr(
        SerpRankCheckService, "sweep_stuck_async", fake_sweep
    )
    result = sweep_stuck_checks()
    assert captured["called"] is True
    assert result["swept"] == 0


@pytest.mark.asyncio
async def test_refresh_task_invokes_service(
    service_session_factory,
    monkeypatch,
):
    captured = {}

    async def fake_refresh(self):
        captured["called"] = True
        return {"locations": 0, "languages": 0}

    monkeypatch.setattr(
        SerpRankCheckService,
        "refresh_reference_data_async",
        fake_refresh,
    )
    result = refresh_reference_data()
    assert captured["called"] is True
