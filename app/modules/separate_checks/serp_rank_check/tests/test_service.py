"""Service-layer tests for the SERP rank check pipeline."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.modules.separate_checks.serp_rank_check.exceptions import (
    SerpParseError,
    SerpProvider4xx,
    SerpProvider5xx,
    SerpProviderTimeout,
)
from app.modules.separate_checks.serp_rank_check.model import (
    PreviewStatus,
    RankCheck,
    RankCheckStatus,
)
from app.modules.separate_checks.serp_rank_check.repository import (
    RankCheckRepository,
)
from app.modules.separate_checks.serp_rank_check.service import (
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


async def _do_check(
    db_session, **overrides
) -> tuple[RankCheck, bool]:
    """Run a synchronous check and return the stored check."""
    params = {
        "user_id": FAKE_USER_ID,
        "keyword": "seo tools",
        "domain": "example.com",
        "location_name": "United States",
        "language_name": "English",
        "device": "desktop",
        "depth": 10,
        "include_preview": False,
    }
    params.update(overrides)
    service = SerpRankCheckService(db_session)
    check, created = await service.check_serp_rank(**params)
    return check, created


async def _reload(service_session_factory, check_id):
    """Read a check back through a fresh session."""
    async with service_session_factory() as session:
        return await RankCheckRepository(session).get(check_id)


# ── check_serp_rank ──────────────────────────────────────
@pytest.mark.asyncio
async def test_check_creates_done_row(
    db_session, fake_serp_client
):
    fake_serp_client.set_response(
        make_serp_body(
            [organic_item(2, "https://example.com/page")]
        )
    )
    check, created = await _do_check(db_session)
    assert created is True
    assert check.status == RankCheckStatus.DONE.value
    assert check.keyword == "seo tools"
    assert check.domain == "example.com"
    assert check.location_name == "United States"
    assert check.language_name == "English"
    assert check.device == "desktop"
    assert check.depth == 10
    assert check.result["found"] is True
    assert check.result["best_position"] == 2
    assert check.fingerprint
    assert check.preview_status == PreviewStatus.NONE.value


@pytest.mark.asyncio
async def test_check_normalizes_keyword_and_domain(
    db_session, fake_serp_client
):
    fake_serp_client.set_response(make_serp_body([]))
    check, _ = await _do_check(
        db_session,
        keyword="  seo   tools  ",
        domain="https://www.Example.com/path",
    )
    assert check.keyword == "seo tools"
    assert check.domain == "example.com"
    assert check.location_name == "United States"
    assert check.language_name == "English"


@pytest.mark.asyncio
async def test_check_stores_raw_response_and_cost(
    db_session, fake_serp_client
):
    fake_serp_client.set_response(make_serp_body([], cost=0.0123))
    check, _ = await _do_check(db_session)
    assert check.raw_response is not None
    assert check.provider_cost is not None
    assert check.provider_called_at is not None


@pytest.mark.asyncio
async def test_check_not_found_is_success(
    db_session, fake_serp_client
):
    fake_serp_client.set_response(
        make_serp_body(
            [
                organic_item(1, "https://other.com/"),
                feature_item("people_also_ask"),
            ]
        )
    )
    check, _ = await _do_check(db_session)
    assert check.status == RankCheckStatus.DONE.value
    assert check.result["found"] is False
    assert check.result["best_position"] is None
    assert check.result["serp_features"] == ["people_also_ask"]


@pytest.mark.asyncio
async def test_check_with_preview_enqueues_preview(
    db_session, fake_serp_client, sent_tasks
):
    fake_serp_client.set_response(
        make_serp_body([organic_item(1, "https://example.com/")])
    )
    check, _ = await _do_check(db_session, include_preview=True)
    assert check.status == RankCheckStatus.DONE.value
    assert check.preview_status == PreviewStatus.PENDING.value
    assert any(
        t["name"] == "serp_rank_check.build_preview"
        and t["queue"] == "serp_preview"
        for t in sent_tasks
    )


@pytest.mark.asyncio
async def test_check_no_preview(
    db_session, fake_serp_client, sent_tasks
):
    fake_serp_client.set_response(
        make_serp_body([organic_item(1, "https://example.com/")])
    )
    check, _ = await _do_check(db_session, include_preview=False)
    assert check.status == RankCheckStatus.DONE.value
    assert check.preview_status == PreviewStatus.NONE.value
    assert not any(
        t["name"] == "serp_rank_check.build_preview"
        for t in sent_tasks
    )


@pytest.mark.asyncio
async def test_check_rejects_blank_location(
    db_session, fake_serp_client
):
    with pytest.raises(ValueError, match="location"):
        await _do_check(db_session, location_name="   ")


@pytest.mark.asyncio
async def test_check_rejects_blank_language(
    db_session, fake_serp_client
):
    with pytest.raises(ValueError, match="language"):
        await _do_check(db_session, language_name="   ")


@pytest.mark.asyncio
async def test_check_rejects_invalid_device(
    db_session, fake_serp_client
):
    with pytest.raises(ValueError):
        await _do_check(db_session, device="tablet")


@pytest.mark.asyncio
async def test_check_rejects_invalid_depth(
    db_session, fake_serp_client
):
    with pytest.raises(ValueError):
        await _do_check(db_session, depth=15)


@pytest.mark.asyncio
async def test_check_rejects_invalid_domain(
    db_session, fake_serp_client
):
    with pytest.raises(ValueError):
        await _do_check(db_session, domain="not-a-domain")


@pytest.mark.asyncio
async def test_check_provider_5xx_marks_running(
    db_session, fake_serp_client
):
    fake_serp_client.set_response(
        exc=_http_error(503)
    )
    with pytest.raises(SerpProvider5xx):
        await _do_check(db_session)


@pytest.mark.asyncio
async def test_check_provider_4xx_marks_failed(
    db_session, fake_serp_client
):
    fake_serp_client.set_response(
        exc=_http_error(400)
    )
    with pytest.raises(SerpProvider4xx):
        await _do_check(db_session)


@pytest.mark.asyncio
async def test_check_timeout_marks_running(
    db_session, fake_serp_client
):
    fake_serp_client.set_response(
        exc=httpx.ReadTimeout("read timed out")
    )
    with pytest.raises(SerpProviderTimeout):
        await _do_check(db_session)


@pytest.mark.asyncio
async def test_check_parse_error_fails(
    db_session, fake_serp_client
):
    body = {
        "status_code": 20000,
        "tasks": [{"status_code": 20000, "result": []}],
    }
    fake_serp_client.set_response(body)
    with pytest.raises(SerpParseError):
        await _do_check(db_session)


@pytest.mark.asyncio
async def test_repeated_checks_create_new_rows(
    db_session, fake_serp_client, service_session_factory
):
    """Repeated checks with same config create separate rows (history)."""
    fake_serp_client.set_response(make_serp_body([]))

    check1, _ = await _do_check(db_session)
    check2, _ = await _do_check(db_session)

    assert check1.id != check2.id
    assert check1.fingerprint == check2.fingerprint
    assert check1.status == RankCheckStatus.DONE.value
    assert check2.status == RankCheckStatus.DONE.value

    reloaded1 = await _reload(service_session_factory, check1.id)
    reloaded2 = await _reload(service_session_factory, check2.id)
    assert reloaded1 is not None
    assert reloaded2 is not None
    assert reloaded1.id != reloaded2.id


# ── build_preview_async ────────────────────────────────
@pytest.mark.asyncio
async def test_build_preview_success(
    service_session_factory,
    preview_artifacts,
    db_session,
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
        fingerprint="fp",
        status=RankCheckStatus.DONE.value,
        preview_status=PreviewStatus.PENDING.value,
        result={
            "found": True,
            "best_position": 7,
            "best_absolute_position": 9,
            "matches": [
                {
                    "position": 7,
                    "absolute_position": 9,
                    "url": "https://example.com/page",
                    "title": "Example Page",
                },
            ],
            "serp_features": [],
            "top_results": [],
            "partial": False,
        },
    )
    db_session.add(check)
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


@pytest.mark.asyncio
async def test_build_preview_idempotent(
    service_session_factory,
    preview_artifacts,
    db_session,
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
        fingerprint="fp",
        status=RankCheckStatus.DONE.value,
        preview_status=PreviewStatus.DONE.value,
        result={"found": True, "best_position": 5},
    )
    db_session.add(check)
    await db_session.commit()

    service = SerpRankCheckService()
    result = await service.build_preview_async(check.id)
    assert result["preview_status"] == "done"


# ── sweep_stuck_async ──────────────────────────────────
@pytest.mark.asyncio
async def test_sweep_marks_stuck_without_raw_response(
    db_session, service_session_factory,
):
    check = RankCheck(
        user_id=FAKE_USER_ID,
        keyword="seo tools",
        domain="example.com",
        location_name="United States",
        language_name="English",
        device="desktop",
        depth=10,
        include_preview=False,
        fingerprint="fp-stuck",
        status=RankCheckStatus.RUNNING.value,
        updated_at=datetime.now(timezone.utc) - timedelta(seconds=120),
    )
    db_session.add(check)
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
    db_session,
    service_session_factory,
    fake_serp_client,
):
    body = make_serp_body(
        [organic_item(1, "https://example.com/")]
    )
    check = RankCheck(
        user_id=FAKE_USER_ID,
        keyword="seo tools",
        domain="example.com",
        location_name="United States",
        language_name="English",
        device="desktop",
        depth=10,
        include_preview=False,
        fingerprint="fp-stuck-raw",
        status=RankCheckStatus.RUNNING.value,
        raw_response=body,
        updated_at=datetime.now(timezone.utc) - timedelta(seconds=120),
    )
    db_session.add(check)
    await db_session.commit()

    service = SerpRankCheckService()
    result = await service.sweep_stuck_async()
    assert result["swept"] == 1
    assert result["resumed"] == 1

    stored = await _reload(service_session_factory, check.id)
    assert stored.status == RankCheckStatus.DONE.value
    assert stored.result["found"] is True


@pytest.mark.asyncio
async def test_sweep_ignores_recent_running(
    db_session, service_session_factory,
):
    check = RankCheck(
        user_id=FAKE_USER_ID,
        keyword="seo tools",
        domain="example.com",
        location_name="United States",
        language_name="English",
        device="desktop",
        depth=10,
        include_preview=False,
        fingerprint="fp-recent",
        status=RankCheckStatus.RUNNING.value,
    )
    db_session.add(check)
    await db_session.commit()

    service = SerpRankCheckService()
    result = await service.sweep_stuck_async()
    assert result["swept"] == 0


# ── classify_error ─────────────────────────────────────
def test_classify_error_walks_cause_chain():
    timeout = SerpProviderTimeout("boom")
    wrapped = RuntimeError("wrapped")
    wrapped.__cause__ = timeout
    assert classify_error(wrapped) == "PROVIDER_TIMEOUT"


def test_classify_error_defaults_to_5xx():
    assert classify_error(RuntimeError("unknown")) == "PROVIDER_5XX"


def test_classify_error_maps_4xx():
    assert classify_error(SerpProvider4xx("4xx error")) == "PROVIDER_4XX"


def test_classify_error_maps_5xx():
    assert classify_error(SerpProvider5xx("5xx error")) == "PROVIDER_5XX"
