"""Tests for RedirectCheckService._execute persistence concurrency safety.

Acceptance test: 10 URLs checked concurrently must NOT cause overlapping
DB operations.  The fake session raises if two ``execute`` calls overlap,
simulating asyncpg's "another operation is in progress" error.
"""
from __future__ import annotations

import asyncio
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.modules.seprate_checks.redirect_check.service import RedirectCheckService
from app.modules.streaming_audit.models.streaming_audit_run import StreamingAuditStatus
from app.modules.streaming_audit.services.streaming_audit_service import StreamingAuditService


class ConcurrentTrackingSession:
    """Fake ``AsyncSession`` that raises if two ``execute`` calls overlap.

    Mirrors the real asyncpg/SQLAlchemy restriction: only one operation
    may be in flight on a single connection at a time.
    """

    def __init__(self) -> None:
        self._active = 0
        self.concurrent_errors: list[RuntimeError] = []
        self.execute_count = 0

    async def execute(self, *args: Any, **kwargs: Any) -> Any:
        self._active += 1
        if self._active > 1:
            self._active -= 1
            err = RuntimeError(
                "Concurrent session.execute detected — asyncpg does not allow "
                "overlapping operations on the same connection!"
            )
            self.concurrent_errors.append(err)
            raise err
        self.execute_count += 1
        await asyncio.sleep(0.01)
        self._active -= 1
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = MagicMock()
        mock_result.scalar_one_or_none.return_value = MagicMock()
        return mock_result

    async def commit(self) -> None:
        pass

    async def refresh(self, *args: Any, **kwargs: Any) -> None:
        pass

    async def add(self, *args: Any, **kwargs: Any) -> None:
        pass

    def begin(self) -> Any:
        return MagicMock()

    async def close(self) -> None:
        pass


def _make_fetch_chain_side_effect(urls: list[str]) -> Any:
    """Return an async side-effect for ``fetch_chain`` that varies results by URL index."""

    async def _side_effect(client, url, max_hops=None, validator=None):
        await asyncio.sleep(0.001)
        idx = urls.index(url)
        if idx % 3 == 0:
            return {
                "url": url,
                "hops": [
                    {"url": url, "status": 301, "location": f"https://example.com/dest{idx}"},
                    {"url": f"https://example.com/dest{idx}", "status": 200},
                ],
            }
        elif idx % 3 == 1:
            return {
                "url": url,
                "hops": [{"url": url, "status": 200}],
            }
        else:
            return {
                "url": url,
                "hops": [{"url": url, "status": 404}],
            }

    return _side_effect


def _expected_state(idx: int) -> str:
    if idx % 3 == 0:
        return "redirected"
    elif idx % 3 == 1:
        return "ok"
    else:
        return "broken"


def _patch_dependencies(service, test_urls, mock_adapter_cls, MockBrowser):
    """Apply common patches for _execute and return context managers."""
    patches = [
        patch.object(service, "_build_seo_map", new_callable=AsyncMock, return_value={}),
        patch(
            "app.modules.seprate_checks.redirect_check.service.fetch_chain",
            side_effect=_make_fetch_chain_side_effect(test_urls),
        ),
        patch(
            "app.modules.seprate_checks.redirect_check.service.probe_soft_404",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "app.modules.seprate_checks.redirect_check.service.RedirectCheckerService"
        ),
        patch(
            "app.modules.seprate_checks.redirect_check.service.StreamingRedirectAdapter"
        ),
    ]

    mock_seo_patch = patches[0]
    fetch_patch = patches[1]
    soft404_patch = patches[2]
    browser_patch = patches[3]
    adapter_patch = patches[4]

    mock_adapter = MagicMock()
    for method_name in ("clear_event_store", "reserve_slot", "release_slot", "publish_event", "close"):
        setattr(mock_adapter, method_name, AsyncMock())
    mock_adapter.reserve_slot.return_value = True
    adapter_patch.start()
    adapter_patch.return_value = mock_adapter

    browser_patch.start()
    browser_patch.return_value.check = AsyncMock()
    browser_patch.return_value.aclose = AsyncMock()

    return patches


@pytest.mark.asyncio
async def test_concurrent_url_checks_no_db_conflicts():
    """Acceptance: 10 URLs checked concurrently must not trigger overlapping DB ops."""
    fake_session = ConcurrentTrackingSession()
    service = RedirectCheckService()

    test_urls = [f"https://example.com/page{i}" for i in range(10)]
    audit_id = str(uuid.uuid4())

    upsert_calls: list[dict] = []

    original_upsert = StreamingAuditService.upsert_page_result

    async def spy_upsert(self_svc, **kwargs):
        upsert_calls.append(kwargs)
        return await original_upsert(self_svc, **kwargs)

    update_run_calls: list[dict] = []
    original_update_run = StreamingAuditService.update_run

    async def spy_update_run(self_svc, audit_id_arg, **values):
        update_run_calls.append(values)
        return await original_update_run(self_svc, audit_id_arg, **values)

    with (
        patch.object(service, "_build_seo_map", new_callable=AsyncMock, return_value={}),
        patch(
            "app.modules.seprate_checks.redirect_check.service.fetch_chain",
            side_effect=_make_fetch_chain_side_effect(test_urls),
        ),
        patch(
            "app.modules.seprate_checks.redirect_check.service.probe_soft_404",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "app.modules.seprate_checks.redirect_check.service.RedirectCheckerService"
        ) as MockBrowser,
        patch(
            "app.modules.seprate_checks.redirect_check.service.StreamingRedirectAdapter"
        ) as MockAdapter,
        patch.object(StreamingAuditService, "upsert_page_result", spy_upsert),
        patch.object(StreamingAuditService, "update_run", spy_update_run),
    ):
        MockBrowser.return_value.check = AsyncMock()
        MockBrowser.return_value.aclose = AsyncMock()

        mock_adapter = MagicMock()
        for method_name in ("clear_event_store", "reserve_slot", "release_slot", "publish_event", "close"):
            setattr(mock_adapter, method_name, AsyncMock())
        mock_adapter.reserve_slot.return_value = True
        MockAdapter.return_value = mock_adapter

        result = await service._execute(
            audit_id=audit_id,
            domain="example.com",
            db=fake_session,
            urls=test_urls,
            site_result=MagicMock(),
            robot_parser=None,
            crawl_result=None,
            update_state=None,
            start_time=0.0,
        )

    assert fake_session.concurrent_errors == [], (
        f"Concurrent DB operations detected: {fake_session.concurrent_errors}"
    )
    assert result["total_checked"] == 10
    assert result["status"] == "completed"
    assert len(upsert_calls) == 10

    persisted_states = {
        call["normalized_url"]: call["page_findings"]["state"]
        for call in upsert_calls
    }
    for i, url in enumerate(test_urls):
        assert url in persisted_states, f"URL {url} was not persisted"
        assert persisted_states[url] == _expected_state(i), (
            f"State mismatch for {url}: expected {_expected_state(i)}, got {persisted_states[url]}"
        )

    final_run_call = update_run_calls[-1]
    assert final_run_call["status"] == StreamingAuditStatus.COMPLETED


@pytest.mark.asyncio
async def test_persistence_failure_sets_partial_status_and_continues():
    """When one upsert fails, the run status is PARTIAL and other URLs still persist."""
    fake_session = ConcurrentTrackingSession()
    service = RedirectCheckService()

    test_urls = [f"https://example.com/p{i}" for i in range(5)]
    audit_id = str(uuid.uuid4())

    upsert_calls: list[dict] = []
    call_index = {"n": 0}
    original_upsert = StreamingAuditService.upsert_page_result

    async def upsert_that_fails_on_third(self_svc, **kwargs):
        call_index["n"] += 1
        if call_index["n"] == 2:
            raise RuntimeError("Simulated DB write failure")
        upsert_calls.append(kwargs)
        return await original_upsert(self_svc, **kwargs)

    update_run_calls: list[dict] = []
    original_update_run = StreamingAuditService.update_run

    async def spy_update_run(self_svc, audit_id_arg, **values):
        update_run_calls.append(values)
        return await original_update_run(self_svc, audit_id_arg, **values)

    with (
        patch.object(service, "_build_seo_map", new_callable=AsyncMock, return_value={}),
        patch(
            "app.modules.seprate_checks.redirect_check.service.fetch_chain",
            side_effect=_make_fetch_chain_side_effect(test_urls),
        ),
        patch(
            "app.modules.seprate_checks.redirect_check.service.probe_soft_404",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "app.modules.seprate_checks.redirect_check.service.RedirectCheckerService"
        ) as MockBrowser,
        patch(
            "app.modules.seprate_checks.redirect_check.service.StreamingRedirectAdapter"
        ) as MockAdapter,
        patch.object(StreamingAuditService, "upsert_page_result", upsert_that_fails_on_third),
        patch.object(StreamingAuditService, "update_run", spy_update_run),
    ):
        MockBrowser.return_value.check = AsyncMock()
        MockBrowser.return_value.aclose = AsyncMock()

        mock_adapter = MagicMock()
        for method_name in ("clear_event_store", "reserve_slot", "release_slot", "publish_event", "close"):
            setattr(mock_adapter, method_name, AsyncMock())
        mock_adapter.reserve_slot.return_value = True
        MockAdapter.return_value = mock_adapter

        result = await service._execute(
            audit_id=audit_id,
            domain="example.com",
            db=fake_session,
            urls=test_urls,
            site_result=MagicMock(),
            robot_parser=None,
            crawl_result=None,
            update_state=None,
            start_time=0.0,
        )

    assert fake_session.concurrent_errors == [], (
        f"Concurrent DB operations detected: {fake_session.concurrent_errors}"
    )
    assert result["total_checked"] == 5
    assert result["status"] == "completed"
    assert len(upsert_calls) == 4

    final_run_call = update_run_calls[-1]
    assert final_run_call["status"] == StreamingAuditStatus.PARTIAL
    final_summary = final_run_call["final_summary"]
    assert final_summary["persistence_failed_count"] == 1
    assert len(final_summary["persistence_failed_urls"]) == 1
