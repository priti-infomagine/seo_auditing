import uuid
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.shared.tasks.celery_app import celery_app


@pytest.mark.asyncio
async def test_meta_check_queues_task(db_session, monkeypatch):
    sent = []

    def fake_send_task(name, args=None, queue=None, **kwargs):
        sent.append({"name": name, "args": args, "queue": queue})
        return SimpleNamespace(id=f"meta-task-{uuid.uuid4()}")

    monkeypatch.setattr(celery_app, "send_task", fake_send_task)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/meta/check",
            json={
                "url": "https://example.com",
                "max_pages": 25,
                "max_depth": 2,
                "respect_robots": False,
            },
        )

    assert response.status_code == 202
    payload = response.json()
    assert payload["status"] == "queued"
    assert payload["max_pages"] == 25
    assert payload["max_depth"] == 2
    assert sent[0]["name"] == "meta.run_check"
    assert sent[0]["queue"] == "crawler"
    assert sent[0]["args"] == [payload["check_id"]]