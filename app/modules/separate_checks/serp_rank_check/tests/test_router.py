"""API endpoint tests for the SERP rank check module."""
from __future__ import annotations

import asyncio
import uuid
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.modules.separate_checks.serp_rank_check.model import (
    RankCheck,
    RankCheckStatus,
)
from app.modules.separate_checks.serp_rank_check.repository import (
    RankCheckRepository,
)

from .conftest import (
    FAKE_USER_ID,
    feature_item,
    make_location,
    make_locations_body,
    make_serp_body,
    make_serp_body_no_match,
    make_serp_body_with_target_at,
    organic_item,
)

API = "/api/v1/serp"


def _valid_payload(**overrides):
    payload = {
        "keyword": "seo tools",
        "domain": "example.com",
        "location": "United States",
        "language": "English",
        "device": "desktop",
        "depth": 10,
    }
    payload.update(overrides)
    return payload


@pytest.mark.asyncio
async def test_create_returns_200_with_result(
    db_session, fake_serp_client
):
    items = [
        organic_item(1, "https://other.com/"),
        organic_item(2, "https://example.com/page"),
    ]
    fake_serp_client.set_response(make_serp_body(items))

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            f"{API}/rank-checks", json=_valid_payload()
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "done"
    assert payload["keyword"] == "seo tools"
    assert payload["domain"] == "example.com"
    assert payload["location"] == "United States"
    assert payload["language"] == "English"
    assert payload["device"] == "desktop"
    assert payload["depth"] == 10
    assert payload["result"]["found"] is True
    assert payload["result"]["best_position"] == 2
    assert payload["result"]["matches"][0]["url"] == (
        "https://example.com/page"
    )


@pytest.mark.asyncio
async def test_create_different_location_creates_new_check(
    db_session, fake_serp_client
):
    fake_serp_client.set_response(make_serp_body([]))

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        r1 = await client.post(
            f"{API}/rank-checks", json=_valid_payload()
        )
        r2 = await client.post(
            f"{API}/rank-checks",
            json=_valid_payload(location="London"),
        )
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json()["id"] != r2.json()["id"]


@pytest.mark.asyncio
async def test_identical_concurrent_returns_same_id(
    db_session, fake_serp_client
):
    """Duplicate in-flight requests are deduplicated via the unique index."""
    items = [organic_item(1, "https://example.com/")]
    fake_serp_client.set_response(
        make_serp_body(items), delay=0.3
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        responses = await asyncio.gather(
            client.post(f"{API}/rank-checks", json=_valid_payload()),
            client.post(f"{API}/rank-checks", json=_valid_payload()),
        )
    ids = {r.json()["id"] for r in responses}
    assert len(ids) == 1
    # Only one provider call (deduplication prevented the second)
    assert len(fake_serp_client.calls) == 1


@pytest.mark.asyncio
async def test_completed_then_new_request_creates_new_check(
    db_session, fake_serp_client
):
    fake_serp_client.set_response(
        make_serp_body([organic_item(1, "https://example.com/")])
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        first = await client.post(
            f"{API}/rank-checks", json=_valid_payload()
        )
        first_id = first.json()["id"]

        second = await client.post(
            f"{API}/rank-checks", json=_valid_payload()
        )
    assert second.status_code == 200
    second_id = second.json()["id"]
    assert second_id != first_id


@pytest.mark.asyncio
async def test_successful_check_persists_result(
    db_session, fake_serp_client
):
    items = [organic_item(1, "https://example.com/")]
    fake_serp_client.set_response(make_serp_body(items))

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            f"{API}/rank-checks", json=_valid_payload()
        )
    assert response.status_code == 200
    check_id = response.json()["id"]

    check = await RankCheckRepository(db_session).get(UUID(check_id))
    assert check is not None
    assert check.status == RankCheckStatus.DONE.value
    assert check.location_name == "United States"
    assert check.language_name == "English"
    assert check.fingerprint
    assert check.raw_response is not None
    assert check.result["found"] is True


@pytest.mark.asyncio
async def test_domain_not_found_records_not_found(
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

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            f"{API}/rank-checks", json=_valid_payload()
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "done"
    assert payload["result"]["found"] is False
    assert payload["result"]["best_position"] is None
    assert payload["result"]["serp_features"] == ["people_also_ask"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        _valid_payload(device="tablet"),
        _valid_payload(keyword="   "),
        _valid_payload(location=""),
        _valid_payload(language=""),
        _valid_payload(depth=15),
    ],
)
async def test_pyantic_validation_errors_return_422(
    db_session, fake_serp_client, payload
):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            f"{API}/rank-checks", json=payload
        )
    assert response.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        _valid_payload(domain="not-a-domain"),
    ],
)
async def test_service_validation_errors_return_400(
    db_session, fake_serp_client, payload
):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            f"{API}/rank-checks", json=payload
        )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_malformed_body_returns_422(db_session):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            f"{API}/rank-checks",
            json={"keyword": "only keyword"},
        )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_by_id_returns_status(
    db_session, fake_serp_client
):
    fake_serp_client.set_response(
        make_serp_body([organic_item(1, "https://example.com/")])
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        created = await client.post(
            f"{API}/rank-checks", json=_valid_payload()
        )
        check_id = created.json()["id"]
        fetched = await client.get(f"{API}/rank-checks/{check_id}")
    assert fetched.status_code == 200
    payload = fetched.json()
    assert payload["id"] == check_id
    assert payload["status"] == "done"
    assert payload["keyword"] == "seo tools"
    assert payload["domain"] == "example.com"
    assert payload["location"] == "United States"
    assert payload["language"] == "English"
    assert payload["device"] == "desktop"
    assert payload["depth"] == 10
    assert payload["result"] is not None


@pytest.mark.asyncio
async def test_get_unknown_id_returns_404(db_session):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            f"{API}/rank-checks/{uuid.uuid4()}"
        )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_paginates_history(db_session):
    for i in range(5):
        db_session.add(
            RankCheck(
                user_id=FAKE_USER_ID,
                keyword=f"keyword {i}",
                domain="example.com",
                location_name="United States",
                language_name="English",
                device="desktop",
                depth=10,
                fingerprint=f"fp-{i}",
                status=RankCheckStatus.DONE.value,
                result={"found": True, "best_position": i + 1},
            )
        )
    await db_session.commit()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            f"{API}/rank-checks", params={"limit": 2, "offset": 0}
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 5
    assert len(payload["items"]) == 2
    assert payload["limit"] == 2
    assert payload["offset"] == 0


@pytest.mark.asyncio
async def test_provider_timeout_returns_504(
    db_session, fake_serp_client
):
    import httpx

    fake_serp_client.set_response(
        exc=httpx.ReadTimeout("read timed out")
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            f"{API}/rank-checks", json=_valid_payload()
        )
    assert response.status_code == 504


@pytest.mark.asyncio
async def test_provider_4xx_returns_502(
    db_session, fake_serp_client
):
    import httpx

    request = httpx.Request(
        "POST",
        "https://api.dataforseo.com/v3/serp/google/organic/"
        "live/advanced",
    )
    response = httpx.Response(400, request=request)
    error = httpx.HTTPStatusError(
        "HTTP 400", request=request, response=response
    )
    fake_serp_client.set_response(exc=error)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            f"{API}/rank-checks", json=_valid_payload()
        )
    assert response.status_code == 502


# ── Auto deep tracking (domain provided) ────────────────────
@pytest.mark.asyncio
async def test_auto_deep_tracking_finds_position_53(
    db_session, fake_serp_client
):
    body = make_serp_body_with_target_at(53, "https://example.com/deep", total=100)
    fake_serp_client.set_response(body)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            f"{API}/rank-checks", json=_valid_payload(depth=10)
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "done"
    assert payload["deep_tracking"] is True
    assert payload["depth"] == 10  # user's depth preserved in response
    result = payload["result"]
    assert result["found"] is True
    assert result["status"] == "found"
    assert result["best_position"] == 53
    assert result["best_absolute_position"] == 53
    assert result["matches"][0]["domain"] == "example.com"
    assert (
        result["matches"][0]["url"]
        == "https://example.com/deep"
    )
    call = fake_serp_client.calls[0]
    assert call["depth"] == 100  # API call uses full depth
    assert call["find_targets_in"] == ["organic"]
    assert call["stop_crawl_on_match"] == [
        {"match_value": "example.com", "match_type": "with_subdomains"}
    ]
    assert call["target_search_mode"] == "any"


@pytest.mark.asyncio
async def test_auto_deep_tracking_not_found_within_limit(
    db_session, fake_serp_client
):
    fake_serp_client.set_response(make_serp_body_no_match(total=100))

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            f"{API}/rank-checks", json=_valid_payload()
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "done"
    assert payload["deep_tracking"] is True
    result = payload["result"]
    assert result["found"] is False
    assert result["status"] == "not_found_within_limit"
    assert result["best_position"] is None


@pytest.mark.asyncio
async def test_auto_deep_tracking_preserves_user_depth(
    db_session, fake_serp_client
):
    """When domain is provided, deep_tracking is auto-enabled and
    the API call uses depth=100, but the response preserves the
    user's requested depth."""
    fake_serp_client.set_response(
        make_serp_body_with_target_at(1, total=100)
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            f"{API}/rank-checks",
            json=_valid_payload(depth=10),
        )
    assert response.status_code == 200
    assert response.json()["depth"] == 10
    assert response.json()["deep_tracking"] is True
    assert fake_serp_client.calls[0]["depth"] == 100


# ── Standard position 3 (auto deep tracking with domain) ─────
@pytest.mark.asyncio
async def test_standard_finds_position_3(
    db_session, fake_serp_client
):
    fake_serp_client.set_response(
        make_serp_body_with_target_at(3, total=100)
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            f"{API}/rank-checks", json=_valid_payload()
        )
    assert response.status_code == 200
    result = response.json()["result"]
    assert result["found"] is True
    assert result["status"] == "found"
    assert result["best_position"] == 3
    assert result["best_absolute_position"] == 3


@pytest.mark.asyncio
async def test_standard_not_found_says_not_found_within_limit(
    db_session, fake_serp_client
):
    """When domain is provided, deep_tracking is auto-enabled, so
    not-found status is 'not_found_within_limit' (search across 100 results)."""
    fake_serp_client.set_response(make_serp_body_no_match(total=100))

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            f"{API}/rank-checks", json=_valid_payload()
        )
    assert response.status_code == 200
    result = response.json()["result"]
    assert result["found"] is False
    assert result["status"] == "not_found_within_limit"


# ── No domain (top results only, no deep tracking) ──────────
@pytest.mark.asyncio
async def test_no_domain_returns_top_results_no_target(
    db_session, fake_serp_client
):
    fake_serp_client.set_response(
        make_serp_body_with_target_at(1, total=100)
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            f"{API}/rank-checks",
            json=_valid_payload(domain=None, depth=10),
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["domain"] is None
    assert payload["deep_tracking"] is False
    assert payload["depth"] == 10
    result = payload["result"]
    assert result["found"] is False
    assert result["status"] == "no_target"
    assert len(result["top_results"]) == 10
    assert result["top_results"][0]["domain"] == "example.com"
    call = fake_serp_client.calls[0]
    assert call["depth"] == 10
    assert call["find_targets_in"] is None
    assert call["stop_crawl_on_match"] is None


# ── Provider failures ──────────────────────────────────────
@pytest.mark.asyncio
async def test_auto_deep_tracking_provider_timeout_returns_504(
    db_session, fake_serp_client
):
    import httpx

    fake_serp_client.set_response(exc=httpx.ReadTimeout("read timed out"))

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            f"{API}/rank-checks", json=_valid_payload()
        )
    assert response.status_code == 504


@pytest.mark.asyncio
async def test_auto_deep_tracking_provider_5xx_returns_502(
    db_session, fake_serp_client
):
    import httpx

    request = httpx.Request(
        "POST",
        "https://api.dataforseo.com/v3/serp/google/organic/"
        "live/advanced",
    )
    response = httpx.Response(503, request=request)
    error = httpx.HTTPStatusError(
        "HTTP 503", request=request, response=response
    )
    fake_serp_client.set_response(exc=error)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            f"{API}/rank-checks", json=_valid_payload()
        )
    assert response.status_code == 502


# ── location_code round-trip ──────────────────────────────────
@pytest.mark.asyncio
async def test_create_rank_check_returns_location_code(
    db_session, fake_serp_client
):
    """A request with location_code echoes it back and forwards it to the
    provider (name still required for display / backward compat)."""
    items = [organic_item(1, "https://example.com/")]
    fake_serp_client.set_response(make_serp_body(items))

    payload = _valid_payload()
    payload["location_code"] = 1007805

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            f"{API}/rank-checks", json=payload
        )
    assert response.status_code == 200
    body = response.json()
    assert body["location_code"] == 1007805
    assert body["location"] == "United States"
    assert fake_serp_client.calls[0]["location_code"] == 1007805


@pytest.mark.asyncio
async def test_create_rank_check_without_location_code_is_none(
    db_session, fake_serp_client
):
    fake_serp_client.set_response(make_serp_body([]))
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            f"{API}/rank-checks", json=_valid_payload()
        )
    assert response.status_code == 200
    assert response.json()["location_code"] is None


# ── /locations autocomplete ──────────────────────────────
@pytest.mark.asyncio
async def test_locations_filters_sorts_city_first(
    db_session, fake_serp_client
):
    """Jaipur City (1007805) and Jaipur Sub District (9182305) share a
    name — the City must sort first so the code disambiguates them."""
    locations = [
        make_location(9182305, "Jaipur,Rajasthan,India", "Sub District"),
        make_location(1007805, "Jaipur,Rajasthan,India", "City"),
        make_location(12345, "Ajmer,Rajasthan,India", "City"),  # no match
    ]
    fake_serp_client.set_locations_response(make_locations_body(locations))

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            f"{API}/locations", params={"q": "jaipur", "country": "in"}
        )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["code"] == 1007805
    assert data[0]["name"] == "Jaipur,Rajasthan,India"
    assert data[0]["type"] == "City"
    assert data[1]["code"] == 9182305
    assert data[1]["type"] == "Sub District"
    # Provider called with the country and cached.
    assert fake_serp_client.location_calls[0]["country"] == "in"


@pytest.mark.asyncio
async def test_locations_caps_results_at_10(
    db_session, fake_serp_client
):
    cities = [
        make_location(100000 + i, f"Jaipur {i},Rajasthan,India", "City")
        for i in range(1, 13)
    ]
    cities.append(
        make_location(9182305, "Jaipur,Rajasthan,India", "Sub District")
    )
    fake_serp_client.set_locations_response(make_locations_body(cities))

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            f"{API}/locations", params={"q": "jaipur", "country": "in"}
        )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 10
    assert all(item["type"] == "City" for item in data)


@pytest.mark.asyncio
async def test_locations_empty_query_returns_empty(
    db_session, fake_serp_client
):
    fake_serp_client.set_locations_response(
        make_locations_body(
            [make_location(1007805, "Jaipur,Rajasthan,India", "City")]
        )
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            f"{API}/locations", params={"q": "", "country": "in"}
        )
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_locations_caches_per_country(
    db_session, fake_serp_client
):
    """The same country is fetched from DataForSEO only once."""
    fake_serp_client.set_locations_response(
        make_locations_body(
            [make_location(1007805, "Jaipur,Rajasthan,India", "City")]
        )
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        r1 = await client.get(
            f"{API}/locations", params={"q": "jaipur", "country": "in"}
        )
        r2 = await client.get(
            f"{API}/locations", params={"q": "jaip", "country": "in"}
        )
    assert r1.status_code == 200 and r2.status_code == 200
    # Second request served from the in-memory cache — no second fetch.
    assert len(fake_serp_client.location_calls) == 1


@pytest.mark.asyncio
async def test_locations_provider_not_configured_returns_503(
    db_session, fake_serp_client, monkeypatch
):
    from app.modules.separate_checks.serp_rank_check.client import (
        SERPDataForSEOConfigurationError,
    )

    async def _raise():
        raise SERPDataForSEOConfigurationError("not configured")

    monkeypatch.setattr(
        "app.modules.separate_checks.serp_rank_check.router.get_serp_client",
        _raise,
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            f"{API}/locations", params={"q": "jaipur", "country": "in"}
        )
    assert response.status_code == 503
