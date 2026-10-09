import inspect
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.endpoints.v1.router import router as v1_router
from app.core.database import get_db
from app.modules.seprate_checks.redirect_urls import router as router_module
from app.modules.seprate_checks.redirect_urls.router import router
from app.modules.seprate_checks.redirect_urls.schema import RedirectUrlCheckRequest


def _create_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/redirect-check")

    async def fake_db():
        yield None

    app.dependency_overrides[get_db] = fake_db
    return app


def test_request_normalizes_origin_and_rejects_credentials():
    request = RedirectUrlCheckRequest(
        domain="https://www.example.com/a/path?ignored=yes",
        max_urls=25,
        max_depth=3,
        max_hops=4,
    )

    assert request.domain == "https://www.example.com/"
    assert request.max_depth == 3
    assert request.max_hops == 4
    with pytest.raises(ValueError):
        RedirectUrlCheckRequest(domain="https://user:pass@example.com")


def test_celery_task_accepts_all_queued_arguments():
    from app.modules.seprate_checks.redirect_urls.tasks import run_redirect_url_audit

    parameters = list(inspect.signature(run_redirect_url_audit.run).parameters)

    assert parameters == [
        "audit_id",
        "domain",
        "max_urls",
        "max_depth",
        "max_hops",
    ]
    assert run_redirect_url_audit.__bound__ is True
    assert run_redirect_url_audit.name == "redirect_check.run_domain_check"
    assert (
        "app.modules.seprate_checks.redirect_urls.tasks"
        in router_module.celery_app.conf.include
    )
    assert (
        "app.modules.seprate_checks.redirect_check.tasks"
        in router_module.celery_app.conf.include
    )


def test_redirect_routes_are_mounted_in_the_versioned_api():
    app = FastAPI()
    app.include_router(v1_router, prefix="/api/v1")

    paths = app.openapi()["paths"]
    assert "/api/v1/redirect-check/check" in paths
    assert "/api/v1/redirect-check/status/{check_id}" in paths
    assert "/api/v1/redirect-check/stream/{check_id}" in paths
    assert "/api/v1/redirect-check/result/{check_id}" in paths


@pytest.mark.asyncio
async def test_post_queues_audit_on_crawler_queue(monkeypatch):
    app = _create_app()
    audit_id = uuid4()
    audit = SimpleNamespace(
        id=audit_id,
        domain="e.g/",
        max_urls=75,
        max_depth=5,
        max_hops=10,
        status="queued",
        progress={"phase": "queued"},
        discovered_count=0,
        completed_count=0,
        failed_count=0,
        error_info=None,
    )

    class FakeRepository:
        def __init__(self, session):
            assert session is None

        async def create(self, **kwargs):
            assert kwargs["audit_id"] == audit_id
            audit.max_depth = kwargs["max_depth"]
            audit.max_hops = kwargs["max_hops"]
            return audit

    async def fake_to_thread(function, *args, **kwargs):
        return function(*args, **kwargs)

    captured: dict = {}

    def fake_send_task(name, args, queue):
        captured.update(name=name, args=args, queue=queue)
        return SimpleNamespace(id="celery-task-id")

    monkeypatch.setattr(router_module, "RedirectUrlAuditRepository", FakeRepository)
    monkeypatch.setattr(router_module, "uuid4", lambda: audit_id)
    monkeypatch.setattr(router_module.asyncio, "to_thread", fake_to_thread)
    monkeypatch.setattr(router_module.celery_app, "send_task", fake_send_task)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/redirect-check/check",
            json={
                "domain": "example.com",
                "max_urls": 75,
                "max_depth": 2,
                "max_hops": 6,
            },
        )

    assert response.status_code == 202
    assert captured["name"] == "redirect_check.run_domain_check"
    assert captured["queue"] == "crawler"
    assert captured["args"] == [str(audit_id), "https://example.com/", 75, 2, 6]
    assert response.json()["task_id"] == "celery-task-id"
    assert response.json()["max_depth"] == 2
    assert response.json()["max_hops"] == 6
    assert response.json()["status_url"] == (
        f"/api/v1/redirect-check/status/{audit_id}"
    )


@pytest.mark.asyncio
async def test_failed_empty_audit_result_is_inspectable(monkeypatch):
    app = _create_app()
    audit_id = uuid4()
    audit = SimpleNamespace(
        id=audit_id,
        domain="e.g/",
        max_urls=75,
        max_depth=5,
        max_hops=10,
        status="failed",
        progress={"phase": "complete"},
        discovered_count=0,
        completed_count=0,
        failed_count=0,
        error_info="No crawlable URLs were discovered.",
        result={
            "check_id": str(audit_id),
            "domain": "e.g/",
            "status": "failed",
            "total_checked": 0,
            "overall_status": "unverified",
            "error": "No crawlable URLs were discovered.",
        },
    )

    class FakeRepository:
        def __init__(self, session):
            assert session is None

        async def get(self, requested_id):
            assert requested_id == audit_id
            return audit

    monkeypatch.setattr(router_module, "RedirectUrlAuditRepository", FakeRepository)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            f"/api/v1/redirect-check/result/{audit_id}"
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "failed"
    assert payload["total_checked"] == 0
    assert payload["overall_status"] == "unverified"
    assert payload["error"] == audit.error_info
