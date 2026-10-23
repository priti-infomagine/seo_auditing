"""Celery task tests for the SERP rank check module.

The main rank-check flow is now synchronous (API calls DataForSEO
directly), so there is no ``run_serp_check`` task.  Only
``sweep_stuck_checks`` remains as a Celery task.
"""
from __future__ import annotations

import pytest

from app.modules.separate_checks.serp_rank_check.service import (
    SerpRankCheckService,
)
from app.modules.separate_checks.serp_rank_check.tasks import (
    sweep_stuck_checks,
)
from app.shared.tasks.celery_app import celery_app
from app.shared.tasks.celery_config import task_routes


class TestTaskConfiguration:
    def test_sweep_task_routing(self):
        assert sweep_stuck_checks.queue == "serp_maintenance"

    def test_task_routes_map_queues(self):
        assert task_routes["serp_rank_check.sweep_stuck_checks"][
            "queue"
        ] == "serp_maintenance"

    def test_beat_schedule_has_sweep_job(self):
        schedule = celery_app.conf.beat_schedule
        assert "serp-sweep-stuck-checks" in schedule
        assert schedule["serp-sweep-stuck-checks"]["schedule"] == 300.0

    def test_serp_tasks_registered(self):
        assert "serp_rank_check.sweep_stuck_checks" in celery_app.tasks


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
