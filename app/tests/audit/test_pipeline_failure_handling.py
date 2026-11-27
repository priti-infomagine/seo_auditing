import asyncio
from datetime import datetime, timezone
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from fastapi import HTTPException
import pytest

from app.modules.audit.repositories.rule_evaluation_repository import _json_safe_value
from app.modules.audit.services.result_state import result_payload_is_incomplete
from app.modules.audit import tasks as audit_tasks
from app.modules.audit.events import AuditEventType
from app.api.endpoints.v1.audit.results import _ensure_result_ready


def test_rule_result_payload_serializes_nested_datetime_and_uuid():
    audit_id = uuid4()
    payload = _json_safe_value({
        "checked_at": datetime(2026, 11, 27, tzinfo=timezone.utc),
        "details": {"audit_id": audit_id},
    })

    encoded = json.dumps(payload)

    assert "2026-11-27T00:00:00+00:00" in encoded
    assert str(audit_id) in encoded


def test_result_is_incomplete_when_pages_have_no_rule_checks():
    payload = {
        "audit": {"pages": {"analyzed": 6}},
        "summary": {"checks": {"total": 0}},
    }

    assert result_payload_is_incomplete(payload)
    assert not result_payload_is_incomplete({
        "audit": {"pages": {"analyzed": 6}},
        "summary": {"checks": {"total": 159}},
    })


def test_result_endpoint_rejects_failed_pipeline_state():
    with pytest.raises(HTTPException) as exc_info:
        _ensure_result_ready({
            "status": "failed",
            "current_stage": "evaluate",
            "error": "Rule persistence failed",
        })

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["status"] == "failed"


def test_analysis_pipeline_does_not_score_after_evaluation_failure(monkeypatch):
    audit_id = str(uuid4())
    db = AsyncMock()

    class _SessionContext:
        async def __aenter__(self):
            return db

        async def __aexit__(self, exc_type, exc, traceback):
            return False

    checker = SimpleNamespace(
        check_links=AsyncMock(return_value=SimpleNamespace(to_dict=lambda: {}))
    )
    parser = SimpleNamespace(
        parse_crawl=AsyncMock(return_value={"pages_parsed": 2})
    )
    evaluator = SimpleNamespace(
        evaluate_crawl=AsyncMock(side_effect=RuntimeError("JSON serialization failed"))
    )
    scorer_factory = MagicMock()
    event_bus = MagicMock()

    class _JobRepository:
        def __init__(self, _db):
            pass

        async def get_by_id(self, _audit_id):
            return None

    monkeypatch.setattr(audit_tasks, "run_async", asyncio.run)
    monkeypatch.setattr(
        "app.core.database.async_session_factory",
        lambda: _SessionContext(),
    )
    monkeypatch.setattr(
        "app.modules.crawler.services.broken_link_checker.BrokenLinkChecker",
        lambda _db: checker,
    )
    monkeypatch.setattr(
        "app.modules.crawler.repositories.crawl_job_repository.CrawlJobRepository",
        _JobRepository,
    )
    monkeypatch.setattr(audit_tasks, "DBParserService", lambda _db: parser)
    monkeypatch.setattr(audit_tasks, "RuleEvaluatorService", lambda _db: evaluator)
    monkeypatch.setattr(audit_tasks, "AnalysisScorerService", scorer_factory)
    monkeypatch.setattr(audit_tasks, "AuditEventBus", lambda: event_bus)
    monkeypatch.setattr("app.core.redis.get_redis", lambda: None)

    result = audit_tasks.run_analysis_pipeline.run(audit_id, force=False)

    assert result["status"] == "failed"
    assert "JSON serialization failed" in result["evaluate"]["error"]
    assert "Skipped because" in result["score"]["error"]
    scorer_factory.assert_not_called()
    assert any(
        call.args[0] == AuditEventType.PIPELINE_FAILED
        for call in event_bus.emit.call_args_list
    )
