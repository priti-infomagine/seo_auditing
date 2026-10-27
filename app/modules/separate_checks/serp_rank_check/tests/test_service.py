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
    make_serp_body_no_match,
    make_serp_body_with_target_at,
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
    }
    params.update(overrides)
    # Auto-compute deep_tracking from domain presence, matching router behavior
    params.setdefault("deep_tracking", params.get("domain") is not None)
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
    assert check.result["found"] is True


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
    assert reloaded2 is not None
    assert reloaded1.id != reloaded2.id


# ── auto deep tracking (domain provided) ──────────────────────
@pytest.mark.asyncio
async def test_auto_deep_tracking_uses_api_depth_100(
    db_session, fake_serp_client
):
    fake_serp_client.set_response(
        make_serp_body_with_target_at(1, total=100)
    )
    await _do_check(db_session)
    assert len(fake_serp_client.calls) == 1
    call = fake_serp_client.calls[0]
    assert call["depth"] == 100


@pytest.mark.asyncio
async def test_auto_deep_tracking_sends_crawl_params(
    db_session, fake_serp_client
):
    fake_serp_client.set_response(
        make_serp_body_with_target_at(1, total=100)
    )
    check, _ = await _do_check(db_session)
    call = fake_serp_client.calls[0]
    assert call["find_targets_in"] == ["organic"]
    assert call["stop_crawl_on_match"] == [
        {"match_value": "example.com", "match_type": "with_subdomains"}
    ]
    assert call["target_search_mode"] == "any"
    assert check.deep_tracking is True
    assert check.depth == 10  # user's depth preserved


@pytest.mark.asyncio
async def test_auto_deep_tracking_finds_position_53(
    db_session, fake_serp_client
):
    body = make_serp_body_with_target_at(53, "https://example.com/deep", total=100)
    fake_serp_client.set_response(body)
    check, _ = await _do_check(db_session)
    result = check.result
    assert result["found"] is True
    assert result["status"] == "found"
    assert result["best_position"] == 53
    assert result["best_absolute_position"] == 53
    assert result["matches"][0]["domain"] == "example.com"


@pytest.mark.asyncio
async def test_auto_deep_tracking_not_found_within_limit(
    db_session, fake_serp_client
):
    fake_serp_client.set_response(
        make_serp_body_no_match(total=100)
    )
    check, _ = await _do_check(db_session)
    result = check.result
    assert result["found"] is False
    assert result["status"] == "not_found_within_limit"
    assert result["best_position"] is None
    assert result["best_absolute_position"] is None


@pytest.mark.asyncio
async def test_auto_deep_tracking_preserves_user_depth(
    db_session, fake_serp_client
):
    """Even with deep tracking, the stored depth is the user's
    requested depth, not 100."""
    fake_serp_client.set_response(
        make_serp_body_with_target_at(1, total=100)
    )
    check, _ = await _do_check(db_session, depth=10)
    assert check.depth == 10
    assert check.deep_tracking is True


# ── no domain (top results only, no deep tracking) ────────────
@pytest.mark.asyncio
async def test_no_domain_returns_no_target_status(
    db_session, fake_serp_client
):
    fake_serp_client.set_response(
        make_serp_body([organic_item(1, "https://example.com/")])
    )
    check, _ = await _do_check(db_session, domain=None)
    assert check.domain is None
    assert check.deep_tracking is False
    result = check.result
    assert result["found"] is False
    assert result["status"] == "no_target"
    assert result["top_results"]
    assert result["top_results"][0]["domain"] == "example.com"


@pytest.mark.asyncio
async def test_no_domain_calls_provider_without_crawl_params(
    db_session, fake_serp_client
):
    fake_serp_client.set_response(make_serp_body([]))
    await _do_check(db_session, domain=None)
    call = fake_serp_client.calls[0]
    assert call["find_targets_in"] is None
    assert call["stop_crawl_on_match"] is None
    assert call["depth"] == 10  # user's depth used when no deep tracking


# ── auto deep tracking (domain provided) ────────────────────────
@pytest.mark.asyncio
async def test_standard_finds_position_3(
    db_session, fake_serp_client
):
    """With domain provided, deep tracking auto-enables and uses
    api_depth=100, finding the domain at position 3."""
    fake_serp_client.set_response(
        make_serp_body_with_target_at(3, total=100)
    )
    check, _ = await _do_check(db_session)
    result = check.result
    assert result["found"] is True
    assert result["status"] == "found"
    assert result["best_position"] == 3
    assert result["best_absolute_position"] == 3
    assert check.deep_tracking is True


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
