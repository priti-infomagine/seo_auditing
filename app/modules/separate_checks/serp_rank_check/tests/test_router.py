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
    make_serp_body,
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
        "include_preview": True,
    }
    payload.update(overrides)
    return payload


@pytest.mark.asyncio
async def test_create_returns_200_with_result(
    db_session, fake_serp_client, sent_tasks
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
    # Preview task was enqueued
    assert any(
        t["name"] == "serp_rank_check.build_preview"
        for t in sent_tasks
    )


@pytest.mark.asyncio
async def test_create_no_preview_does_not_enqueue_preview(
    db_session, fake_serp_client, sent_tasks
):
    fake_serp_client.set_response(
        make_serp_body([organic_item(1, "https://example.com/")])
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            f"{API}/rank-checks",
            json=_valid_payload(include_preview=False),
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "done"
    # No preview task enqueued
    assert not any(
        t["name"] == "serp_rank_check.build_preview"
        for t in sent_tasks
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
    db_session, fake_serp_client, sent_tasks
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
        _valid_payload(depth=15),
        _valid_payload(domain="not-a-domain"),
        _valid_payload(keyword="a" * 101),
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
                include_preview=True,
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


@pytest.mark.asyncio
async def test_preview_artifact_missing_returns_404(
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
        response = await client.get(
            f"{API}/previews/{check_id}/preview.html"
        )
    assert response.status_code == 404
