"""API endpoint tests for the SERP rank check module."""
from __future__ import annotations

import asyncio
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.modules.seprate_checks.serp_rank_check.model import (
    RankCheck,
    RankCheckStatus,
)
from app.modules.seprate_checks.serp_rank_check.repository import (
    RankCheckRepository,
)

from .conftest import FAKE_USER_ID

API = "/api/v1/serp"


def _valid_payload(**overrides):
    payload = {
        "keyword": "seo tools",
        "domain": "example.com",
        "location_code": 2840,
        "language_code": "en",
        "device": "desktop",
        "depth": 10,
        "include_preview": True,
    }
    payload.update(overrides)
    return payload


@pytest.mark.asyncio
async def test_create_returns_202_and_enqueues(
    seed_reference, sent_tasks
):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            f"{API}/rank-checks", json=_valid_payload()
        )
    assert response.status_code == 202
    payload = response.json()
    assert payload["status"] == "queued"
    assert len(sent_tasks) == 1
    assert sent_tasks[0]["name"] == "serp_rank_check.run_serp_check"
    assert sent_tasks[0]["queue"] == "serp_io"
    assert sent_tasks[0]["args"] == [payload["id"]]


@pytest.mark.asyncio
async def test_create_no_preview_still_enqueues(
    seed_reference, sent_tasks
):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            f"{API}/rank-checks",
            json=_valid_payload(include_preview=False),
        )
    assert response.status_code == 202
    assert len(sent_tasks) == 1


@pytest.mark.asyncio
async def test_identical_concurrent_posts_return_same_id(
    seed_reference, sent_tasks
):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        responses = await asyncio.gather(
            client.post(f"{API}/rank-checks", json=_valid_payload()),
            client.post(f"{API}/rank-checks", json=_valid_payload()),
        )
    ids = {r.json()["id"] for r in responses}
    assert len(ids) == 1
    # Only one task is enqueued for the duplicate pair.
    assert len(sent_tasks) == 1
    assert all(r.status_code in (200, 202) for r in responses)


@pytest.mark.asyncio
async def test_same_request_after_completion_creates_new_job(
    seed_reference, sent_tasks, db_session
):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        first = await client.post(
            f"{API}/rank-checks", json=_valid_payload()
        )
    first_id = first.json()["id"]

    # Drive the first job to completion.
    repo = RankCheckRepository(db_session)
    check = await repo.get(uuid.UUID(first_id))
    check.status = RankCheckStatus.DONE.value
    await db_session.commit()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        second = await client.post(
            f"{API}/rank-checks", json=_valid_payload()
        )
    assert second.status_code == 202
    second_id = second.json()["id"]
    assert second_id != first_id
    assert len(sent_tasks) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        _valid_payload(device="tablet"),
        _valid_payload(depth=15),
        _valid_payload(location_code=999999),
        _valid_payload(language_code="zz"),
        _valid_payload(domain="not-a-domain"),
        _valid_payload(keyword="   "),
        _valid_payload(keyword="a" * 101),
    ],
)
async def test_validation_errors_return_400(
    seed_reference, payload
):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            f"{API}/rank-checks", json=payload
        )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_malformed_body_returns_422(seed_reference):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            f"{API}/rank-checks", json={"keyword": "only keyword"}
        )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_by_id_returns_status(
    seed_reference, sent_tasks
):
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
    assert payload["status"] == "queued"
    assert payload["keyword"] == "seo tools"
    assert payload["domain"] == "example.com"
    assert payload["device"] == "desktop"
    assert payload["depth"] == 10
    assert payload["preview_status"] == "none"
    assert payload["result"] is None


@pytest.mark.asyncio
async def test_get_by_id_returns_result_once_ranked(
    seed_reference, db_session
):
    repo = RankCheckRepository(db_session)
    check = RankCheck(
        user_id=FAKE_USER_ID,
        keyword="seo tools",
        domain="example.com",
        location_code=2840,
        language_code="en",
        device="desktop",
        depth=10,
        include_preview=True,
        fingerprint="fp",
        status=RankCheckStatus.RANKED.value,
        result={
            "found": True,
            "best_position": 3,
            "best_absolute_position": 3,
            "matches": [
                {
                    "position": 3,
                    "absolute_position": 3,
                    "url": "https://example.com/",
                    "title": "Example",
                }
            ],
            "serp_features": [],
            "top_results": [],
            "partial": False,
        },
    )
    db_session.add(check)
    await db_session.commit()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            f"{API}/rank-checks/{check.id}"
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ranked"
    assert payload["result"]["found"] is True
    assert payload["result"]["best_position"] == 3


@pytest.mark.asyncio
async def test_get_unknown_id_returns_404(seed_reference):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            f"{API}/rank-checks/{uuid.uuid4()}"
        )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_any_check_returns_status(
    seed_reference, db_session
):
    repo = RankCheckRepository(db_session)
    other_user = uuid.uuid4()
    check = RankCheck(
        user_id=other_user,
        keyword="seo tools",
        domain="example.com",
        location_code=2840,
        language_code="en",
        device="desktop",
        depth=10,
        include_preview=True,
        fingerprint="fp-other",
        status=RankCheckStatus.QUEUED.value,
    )
    db_session.add(check)
    await db_session.commit()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(f"{API}/rank-checks/{check.id}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == str(check.id)
    assert payload["keyword"] == "seo tools"


@pytest.mark.asyncio
async def test_list_paginates_history(seed_reference, db_session):
    repo = RankCheckRepository(db_session)
    for i in range(5):
        db_session.add(
            RankCheck(
                user_id=FAKE_USER_ID,
                keyword=f"keyword {i}",
                domain="example.com",
                location_code=2840,
                language_code="en",
                device="desktop",
                depth=10,
                include_preview=True,
                fingerprint=f"fp-{i}",
                status=RankCheckStatus.DONE.value,
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
async def test_list_locations(seed_reference):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(f"{API}/locations")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 2
    codes = {item["location_code"] for item in payload["items"]}
    assert codes == {2840, 2841}


@pytest.mark.asyncio
async def test_list_locations_query_filter(seed_reference):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            f"{API}/locations", params={"q": "United"}
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["location_code"] == 2840


@pytest.mark.asyncio
async def test_list_languages(seed_reference):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(f"{API}/languages")
    assert response.status_code == 200
    payload = response.json()
    codes = {item["language_code"] for item in payload["items"]}
    assert codes == {"en", "fr"}


@pytest.mark.asyncio
async def test_preview_artifact_missing_returns_404(
    seed_reference, sent_tasks
):
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
