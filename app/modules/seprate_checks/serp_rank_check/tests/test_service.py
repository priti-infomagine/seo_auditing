"""Service-layer tests for the SERP rank check pipeline."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.modules.seprate_checks.serp_rank_check.exceptions import (
    SerpParseError,
    SerpProvider4xx,
    SerpProvider5xx,
    SerpProviderTimeout,
)
from app.modules.seprate_checks.serp_rank_check.model import (
    PreviewStatus,
    RankCheckStatus,
)
from app.modules.seprate_checks.serp_rank_check.repository import (
    RankCheckRepository,
    SerpLanguageRepository,
    SerpLocationRepository,
)
from app.modules.seprate_checks.serp_rank_check.service import (
    SerpRankCheckService,
    classify_error,
)

from .conftest import (
    FAKE_USER_ID,
    feature_item,
    make_serp_body,
    organic_item,
)


def _http_error(status: int) -> httpx.HTTPStatusError:
    request = httpx.Request(
        "POST", "https://api.dataforseo.com/v3/serp/google/organic/live/advanced"
    )
    response = httpx.Response(status, request=request)
    return httpx.HTTPStatusError(
        f"HTTP {status}", request=request, response=response
    )


async def _create_check(
    db_session, **overrides
):
    service = SerpRankCheckService(db_session)
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
    return await service.prepare_check(**params)


async def _reload(service_session_factory, check_id):
    """Read a check back through a fresh session.

    The service commits via its own session, so the
    test's ``db_session`` would return a stale copy
    from its identity map. A fresh session always
    observes the committed state — mirroring how the
    Celery worker reads the row in a separate process.
    """
    async with service_session_factory() as session:
        return await RankCheckRepository(session).get(check_id)


# ── prepare_check ──────────────────────────────────────
@pytest.mark.asyncio
async def test_prepare_check_creates_queued_row(
    seed_reference, db_session
):
    check, created = await _create_check(db_session)
    assert created is True
    assert check.status == RankCheckStatus.QUEUED.value
    assert check.keyword == "seo tools"
    assert check.domain == "example.com"
    assert check.device == "desktop"
    assert check.depth == 10
    assert check.include_preview is False
    assert check.fingerprint
    assert check.preview_status == PreviewStatus.NONE.value


@pytest.mark.asyncio
async def test_prepare_check_normalizes_keyword_and_domain(
    seed_reference, db_session
):
    check, _ = await _create_check(
        db_session,
        keyword="  seo   tools  ",
        domain="https://www.Example.com/path",
    )
    assert check.keyword == "seo tools"
    assert check.domain == "example.com"


@pytest.mark.asyncio
async def test_prepare_check_duplicate_returns_existing(
    seed_reference, db_session
):
    first, created_first = await _create_check(db_session)
    second, created_second = await _create_check(db_session)
    assert created_first is True
    assert created_second is False
    assert second.id == first.id


@pytest.mark.asyncio
async def test_prepare_check_rejects_unknown_location(
    seed_reference, db_session
):
    with pytest.raises(ValueError):
        await _create_check(db_session, location_code=999999)


@pytest.mark.asyncio
async def test_prepare_check_rejects_unknown_language(
    seed_reference, db_session
):
    with pytest.raises(ValueError):
        await _create_check(db_session, language_code="zz")


# ── run_check_async ────────────────────────────────────
@pytest.mark.asyncio
async def test_run_check_full_flow_no_preview(
    seed_reference,
    service_session_factory,
    fake_serp_client,
    sent_tasks,
    db_session,
):
    items = [
        organic_item(1, "https://other.com/"),
        organic_item(
            2, "https://example.com/page", title="Example Page"
        ),
        organic_item(3, "https://another.com/"),
    ]
    fake_serp_client.set_response(make_serp_body(items))

    check, _ = await _create_check(db_session)
    service = SerpRankCheckService()
    result = await service.run_check_async(check.id)

    assert result["status"] == "done"
    # Exactly one provider call with the correct parameters.
    assert len(fake_serp_client.calls) == 1
    call = fake_serp_client.calls[0]
    assert call["keyword"] == "seo tools"
    assert call["location_code"] == 2840
    assert call["language_code"] == "en"
    assert call["device"] == "desktop"
    assert call["depth"] == 10

    stored = await _reload(service_session_factory, check.id)
    assert stored.status == RankCheckStatus.DONE.value
    assert stored.raw_response is not None
    assert stored.provider_called_at is not None
    assert stored.provider_cost is not None
    assert stored.result["found"] is True
    assert stored.result["best_position"] == 2
    assert stored.result["matches"][0]["url"] == (
        "https://example.com/page"
    )
    assert stored.preview_status == PreviewStatus.NONE.value
    # No preview requested -> no preview task enqueued.
    assert not any(
        t["name"] == "serp_rank_check.build_preview"
        for t in sent_tasks
    )


@pytest.mark.asyncio
async def test_run_check_with_preview_enqueues_preview(
    seed_reference,
    service_session_factory,
    fake_serp_client,
    sent_tasks,
    db_session,
):
    fake_serp_client.set_response(
        make_serp_body([organic_item(1, "https://example.com/")])
    )
    check, _ = await _create_check(
        db_session, include_preview=True
    )
    service = SerpRankCheckService()
    result = await service.run_check_async(check.id)

    assert result["status"] == "ranked"
    stored = await _reload(service_session_factory, check.id)
    assert stored.status == RankCheckStatus.RANKED.value
    assert stored.preview_status == PreviewStatus.PENDING.value
    assert any(
        t["name"] == "serp_rank_check.build_preview"
        and t["queue"] == "serp_preview"
        for t in sent_tasks
    )


@pytest.mark.asyncio
async def test_run_check_sends_mobile_device(
    seed_reference,
    service_session_factory,
    fake_serp_client,
    db_session,
):
    fake_serp_client.set_response(make_serp_body([]))
    check, _ = await _create_check(db_session, device="mobile")
    service = SerpRankCheckService()
    await service.run_check_async(check.id)
    assert fake_serp_client.calls[0]["device"] == "mobile"


@pytest.mark.asyncio
async def test_run_check_not_found_is_noop(
    service_session_factory, fake_serp_client
):
    service = SerpRankCheckService()
    result = await service.run_check_async(uuid.uuid4())
    assert result["status"] == "missing"
    assert fake_serp_client.calls == []


@pytest.mark.asyncio
async def test_run_check_redelivery_after_ranked_is_noop(
    seed_reference,
    service_session_factory,
    fake_serp_client,
    sent_tasks,
    db_session,
):
    fake_serp_client.set_response(
        make_serp_body([organic_item(1, "https://example.com/")])
    )
    check, _ = await _create_check(db_session)
    service = SerpRankCheckService()
    await service.run_check_async(check.id)
    assert len(fake_serp_client.calls) == 1

    # Redelivery after ranked must not call the provider again.
    result = await service.run_check_async(check.id)
    assert result["status"] == "done"
    assert len(fake_serp_client.calls) == 1


@pytest.mark.asyncio
async def test_run_check_resumes_from_raw_response(
    seed_reference,
    service_session_factory,
    fake_serp_client,
    db_session,
):
    # Simulate a crash after the provider call: the row is
    # running with a stored raw response but no result.
    body = make_serp_body(
        [organic_item(1, "https://example.com/")]
    )
    check, _ = await _create_check(db_session)
    check.status = RankCheckStatus.RUNNING.value
    check.raw_response = body
    await db_session.commit()

    service = SerpRankCheckService()
    result = await service.run_check_async(check.id)
    # Resumed parsing without a second provider call.
    assert result["status"] == "done"
    assert fake_serp_client.calls == []
    stored = await _reload(service_session_factory, check.id)
    assert stored.status == RankCheckStatus.DONE.value
    assert stored.result["found"] is True


@pytest.mark.asyncio
async def test_run_check_provider_4xx_fails_immediately(
    seed_reference,
    service_session_factory,
    fake_serp_client,
    db_session,
):
    fake_serp_client.set_response(exc=_http_error(400))
    check, _ = await _create_check(db_session)
    service = SerpRankCheckService()
    with pytest.raises(SerpProvider4xx):
        await service.run_check_async(check.id)

    stored = await _reload(service_session_factory, check.id)
    assert stored.status == RankCheckStatus.FAILED.value
    assert stored.error_code == "PROVIDER_4XX"


@pytest.mark.asyncio
async def test_run_check_provider_5xx_is_retryable(
    seed_reference,
    service_session_factory,
    fake_serp_client,
    db_session,
):
    fake_serp_client.set_response(exc=_http_error(503))
    check, _ = await _create_check(db_session)
    service = SerpRankCheckService()
    with pytest.raises(SerpProvider5xx):
        await service.run_check_async(check.id)

    # Retryable: the row stays running for Celery to redeliver.
    stored = await _reload(service_session_factory, check.id)
    assert stored.status == RankCheckStatus.RUNNING.value
    assert stored.error_code is None


@pytest.mark.asyncio
async def test_run_check_provider_timeout_is_retryable(
    seed_reference,
    service_session_factory,
    fake_serp_client,
    db_session,
):
    fake_serp_client.set_response(
        exc=httpx.ReadTimeout("read timed out")
    )
    check, _ = await _create_check(db_session)
    service = SerpRankCheckService()
    with pytest.raises(SerpProviderTimeout):
        await service.run_check_async(check.id)

    stored = await _reload(service_session_factory, check.id)
    assert stored.status == RankCheckStatus.RUNNING.value


@pytest.mark.asyncio
async def test_run_check_parse_error_fails(
    seed_reference,
    service_session_factory,
    fake_serp_client,
    db_session,
):
    # Valid HTTP envelope but a malformed task result.
    body = {
        "status_code": 20000,
        "tasks": [{"status_code": 20000, "result": []}],
    }
    fake_serp_client.set_response(body)
    check, _ = await _create_check(db_session)
    service = SerpRankCheckService()
    result = await service.run_check_async(check.id)

    stored = await _reload(service_session_factory, check.id)
    assert stored.status == RankCheckStatus.FAILED.value
    assert stored.error_code == "PARSE_ERROR"


@pytest.mark.asyncio
async def test_run_check_domain_not_found_is_success(
    seed_reference,
    service_session_factory,
    fake_serp_client,
    db_session,
):
    fake_serp_client.set_response(
        make_serp_body(
            [
                organic_item(1, "https://other.com/"),
                feature_item("people_also_ask"),
            ]
        )
    )
    check, _ = await _create_check(db_session)
    service = SerpRankCheckService()
    result = await service.run_check_async(check.id)

    assert result["status"] == "done"
    stored = await _reload(service_session_factory, check.id)
    assert stored.status == RankCheckStatus.DONE.value
    assert stored.result["found"] is False
    assert stored.result["best_position"] is None
    assert stored.result["serp_features"] == ["people_also_ask"]


# ── build_preview_async ────────────────────────────────
@pytest.mark.asyncio
async def test_build_preview_success(
    seed_reference,
    service_session_factory,
    preview_artifacts,
    db_session,
):
    check, _ = await _create_check(
        db_session, include_preview=True
    )
    check.status = RankCheckStatus.RANKED.value
    check.preview_status = PreviewStatus.PENDING.value
    check.result = {
        "found": True,
        "best_position": 1,
        "best_absolute_position": 1,
        "matches": [],
        "serp_features": [],
        "top_results": [],
        "partial": False,
    }
    await db_session.commit()

    service = SerpRankCheckService()
    result = await service.build_preview_async(check.id)

    assert result["status"] == "done"
    assert result["preview_status"] == "done"
    stored = await _reload(service_session_factory, check.id)
    assert stored.preview_status == PreviewStatus.DONE.value
    assert stored.status == RankCheckStatus.DONE.value
    assert stored.preview_html_url == preview_artifacts["urls"][
        "html_url"
    ]
    assert stored.preview_image_url == preview_artifacts["urls"][
        "image_url"
    ]
    assert stored.result is not None


@pytest.mark.asyncio
async def test_build_preview_failure_keeps_result(
    seed_reference,
    service_session_factory,
    preview_artifacts,
    db_session,
):
    preview_artifacts["raise"] = RuntimeError("screenshot boom")
    check, _ = await _create_check(
        db_session, include_preview=True
    )
    check.status = RankCheckStatus.RANKED.value
    check.preview_status = PreviewStatus.PENDING.value
    check.result = {"found": True, "best_position": 5}
    await db_session.commit()

    service = SerpRankCheckService()
    result = await service.build_preview_async(check.id)

    assert result["status"] == "done"
    assert result["preview_status"] == "failed"
    stored = await _reload(service_session_factory, check.id)
    assert stored.preview_status == PreviewStatus.FAILED.value
    assert stored.status == RankCheckStatus.DONE.value
    # Rank result is intact.
    assert stored.result["found"] is True
    assert stored.result["best_position"] == 5


@pytest.mark.asyncio
async def test_build_preview_idempotent(
    seed_reference,
    service_session_factory,
    preview_artifacts,
    db_session,
):
    check, _ = await _create_check(db_session)
    check.preview_status = PreviewStatus.DONE.value
    await db_session.commit()

    service = SerpRankCheckService()
    result = await service.build_preview_async(check.id)
    assert result["preview_status"] == "done"


# ── sweep_stuck_async ──────────────────────────────────
@pytest.mark.asyncio
async def test_sweep_marks_stuck_without_raw_response(
    seed_reference, service_session_factory, db_session
):
    check, _ = await _create_check(db_session)
    check.status = RankCheckStatus.RUNNING.value
    check.updated_at = datetime.now(timezone.utc) - timedelta(
        seconds=120
    )
    await db_session.commit()

    service = SerpRankCheckService()
    result = await service.sweep_stuck_async()
    assert result["swept"] == 1
    assert result["failed"] == 1

    stored = await _reload(service_session_factory, check.id)
    assert stored.status == RankCheckStatus.FAILED.value
    assert stored.error_code == "STUCK"


@pytest.mark.asyncio
async def test_sweep_resumes_stuck_with_raw_response(
    seed_reference,
    service_session_factory,
    fake_serp_client,
    db_session,
):
    fake_serp_client.set_response(make_serp_body([]))
    check, _ = await _create_check(db_session)
    check.status = RankCheckStatus.RUNNING.value
    check.raw_response = make_serp_body(
        [organic_item(1, "https://example.com/")]
    )
    check.updated_at = datetime.now(timezone.utc) - timedelta(
        seconds=120
    )
    await db_session.commit()

    service = SerpRankCheckService()
    result = await service.sweep_stuck_async()
    assert result["swept"] == 1
    assert result["resumed"] == 1

    stored = await _reload(service_session_factory, check.id)
    assert stored.status == RankCheckStatus.DONE.value
    assert stored.result["found"] is True
    # No provider call during the sweep resume.
    assert fake_serp_client.calls == []


@pytest.mark.asyncio
async def test_sweep_ignores_recent_running(
    seed_reference, service_session_factory, db_session
):
    check, _ = await _create_check(db_session)
    check.status = RankCheckStatus.RUNNING.value
    await db_session.commit()

    service = SerpRankCheckService()
    result = await service.sweep_stuck_async()
    assert result["swept"] == 0

    stored = await _reload(service_session_factory, check.id)
    assert stored.status == RankCheckStatus.RUNNING.value


# ── refresh_reference_data_async ───────────────────────
@pytest.mark.asyncio
async def test_refresh_reference_data_upserts(
    service_session_factory,
    fake_serp_client,
    db_session,
):
    service = SerpRankCheckService()
    result = await service.refresh_reference_data_async()
    assert result["locations"] == 2
    assert result["languages"] == 2

    loc_repo = SerpLocationRepository(db_session)
    locations = await loc_repo.list(None, 200, 0)
    assert {loc.location_code for loc in locations} == {2840, 2841}

    lang_repo = SerpLanguageRepository(db_session)
    languages = await lang_repo.list(500, 0)
    assert {lang.language_code for lang in languages} == {"en", "fr"}


# ── classify_error ─────────────────────────────────────
def test_classify_error_walks_cause_chain():
    timeout = SerpProviderTimeout("boom")
    wrapped = RuntimeError("wrapped")
    wrapped.__cause__ = timeout
    assert classify_error(wrapped) == "PROVIDER_TIMEOUT"


def test_classify_error_defaults_to_5xx():
    assert classify_error(RuntimeError("unknown")) == "PROVIDER_5XX"


def test_classify_error_maps_4xx():
    assert classify_error(httpx.HTTPStatusError(
        "400",
        request=httpx.Request("POST", "https://x"),
        response=httpx.Response(400),
    )) == "PROVIDER_4XX"
