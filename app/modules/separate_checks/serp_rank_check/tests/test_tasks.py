"""Celery task tests for the SERP rank check module.

The main rank-check flow is now synchronous (API calls DataForSEO
directly), so ``run_serp_check`` and ``refresh_reference_data``
tasks no longer exist.  Only ``build_preview`` and
``sweep_stuck_checks`` remain as Celery tasks.
"""
from __future__ import annotations

import pytest

from app.modules.separate_checks.serp_rank_check.model import (
    PreviewStatus,
    RankCheck,
    RankCheckStatus,
)
from app.modules.separate_checks.serp_rank_check.service import (
    SerpRankCheckService,
)
from app.modules.separate_checks.serp_rank_check.tasks import (
    build_preview,
    sweep_stuck_checks,
)
from app.shared.tasks.celery_app import celery_app
from app.shared.tasks.celery_config import task_routes

from .conftest import FAKE_USER_ID


class TestTaskConfiguration:
    def test_build_preview_routing(self):
        assert build_preview.queue == "serp_preview"
        assert build_preview.max_retries == 0
        assert build_preview.acks_late is True

    def test_sweep_task_routing(self):
        assert sweep_stuck_checks.queue == "serp_maintenance"

    def test_task_routes_map_queues(self):
        assert task_routes["serp_rank_check.build_preview"][
            "queue"
        ] == "serp_preview"
        assert task_routes["serp_rank_check.sweep_stuck_checks"][
            "queue"
        ] == "serp_maintenance"

    def test_beat_schedule_has_sweep_job(self):
        schedule = celery_app.conf.beat_schedule
        assert "serp-sweep-stuck-checks" in schedule
        assert schedule["serp-sweep-stuck-checks"]["schedule"] == 300.0

    def test_serp_tasks_registered(self):
        assert "serp_rank_check.build_preview" in celery_app.tasks
        assert "serp_rank_check.sweep_stuck_checks" in celery_app.tasks

    def test_removed_tasks_not_registered(self):
        assert "serp_rank_check.run_serp_check" not in celery_app.tasks
        assert (
            "serp_rank_check.refresh_reference_data"
            not in celery_app.tasks
        )


@pytest.mark.asyncio
async def test_build_preview_task_invokes_service(
    db_session, service_session_factory, preview_artifacts, monkeypatch
):
    check = RankCheck(
        user_id=FAKE_USER_ID,
        keyword="seo tools",
        domain="example.com",
        location_name="United States",
        language_name="English",
        device="desktop",
        depth=10,
        include_preview=True,
        fingerprint="fp-task",
        status=RankCheckStatus.DONE.value,
        preview_status=PreviewStatus.PENDING.value,
        result={"found": True, "best_position": 1},
    )
    db_session.add(check)
    await db_session.commit()

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
    result = build_preview(str(check.id))
    assert captured["check_id"] == check.id
    assert result["preview_status"] == "done"


@pytest.mark.asyncio
async def test_sweep_task_invokes_service(
    service_session_factory, monkeypatch
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
