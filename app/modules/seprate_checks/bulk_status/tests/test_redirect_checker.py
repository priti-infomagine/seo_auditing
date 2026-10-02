from contextlib import asynccontextmanager
from types import SimpleNamespace
from urllib.parse import urlsplit
from unittest.mock import AsyncMock

from fastapi import FastAPI
import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from app.modules.seprate_checks.bulk_status.schema import (
    USER_AGENTS,
    RedirectCheckRequest,
    RedirectData,
    RedirectResponse,
    UserAgentInfo,
    normalize_http_url,
)
from app.modules.seprate_checks.bulk_status.service import RedirectCheckerService
from app.modules.seprate_checks.bulk_status.service import RedirectCheckInfrastructureError
from app.modules.seprate_checks.bulk_status.router import router


@pytest.fixture(autouse=True)
def skip_dns_ssrf_lookup(monkeypatch):
    monkeypatch.setattr(
        "app.modules.seprate_checks.bulk_status.service.validate_url_ssrf",
        lambda url, allow_private=False: None,
    )


def test_url_request_normalizes_and_deduplicates():
    request = RedirectCheckRequest(
        mode="urls",
        urls=[" HTTPS://Example.COM ", "https://example.com/"],
    )

    assert request.urls == ["https://example.com/"]


@pytest.mark.parametrize("url", ["ftp://example.com", "https:///missing-host", "example.com"])
def test_url_request_rejects_unsupported_or_missing_scheme(url):
    with pytest.raises(ValueError):
        normalize_http_url(url)


@pytest.mark.asyncio
async def test_http_mode_records_multiple_redirect_hops_and_aliases():
    responses = {
        "https://example.com/old": httpx.Response(
            301,
            headers={"location": "/middle", "set-cookie": "secret"},
            request=httpx.Request("GET", "https://example.com/old"),
        ),
        "https://example.com/middle": httpx.Response(
            302,
            headers={"location": "https://example.com/new"},
            request=httpx.Request("GET", "https://example.com/middle"),
        ),
        "https://example.com/new": httpx.Response(
            200,
            headers={"content-type": "text/html"},
            content=b"<html><title>Done</title></html>",
            request=httpx.Request("GET", "https://example.com/new"),
        ),
    }

    async def handler(request):
        return responses[str(request.url)]

    service = RedirectCheckerService(http_transport=httpx.MockTransport(handler))
    result = await service.check(
        RedirectCheckRequest(mode="urls", urls=["https://example.com/old"])
    )
    payload = result.model_dump(by_alias=True)
    item = payload["data"]["results"][0]

    assert item["redirects"] == 2
    assert len(item["hops"]) == 3
    assert item["hops"][0]["location"] == "/middle"
    assert item["hops"][0]["resolved"] == "https://example.com/middle"
    assert item["finalUrl"] == "https://example.com/new"
    assert item["finalStatus"] == 200
    assert "set-cookie" not in {header["name"] for header in item["hops"][0]["headers"]}
    assert payload["data"]["userAgent"] == {"key": "chrome", "label": "Desktop Chrome"}
    assert "maxUrls" in payload["data"]


@pytest.mark.asyncio
async def test_redirect_loop_is_reported_per_url():
    async def handler(request):
        location = "/two" if urlsplit(str(request.url)).path == "/one" else "/one"
        return httpx.Response(
            302,
            headers={"location": location},
            request=request,
        )

    service = RedirectCheckerService(http_transport=httpx.MockTransport(handler))
    result = await service.check(
        RedirectCheckRequest(mode="urls", urls=["https://example.com/one"])
    )

    assert result.data.results[0].redirects == 2
    assert result.data.results[0].error == "Redirect loop detected."


@pytest.mark.asyncio
async def test_transport_failure_is_an_individual_result():
    async def handler(request):
        raise httpx.ConnectError("private details", request=request)

    service = RedirectCheckerService(http_transport=httpx.MockTransport(handler))
    result = await service.check(
        RedirectCheckRequest(mode="urls", urls=["https://example.com/page"])
    )

    assert result.data.checked == 1
    assert result.data.results[0].error == "Connection failed."
    assert result.data.results[0].final_status is None


@pytest.mark.asyncio
async def test_http_500_does_not_trigger_browser_fallback(monkeypatch):
    async def handler(request):
        return httpx.Response(
            500,
            headers={"content-type": "text/html"},
            content=b"<script>location.href='/later'</script>",
            request=request,
        )

    service = RedirectCheckerService(http_transport=httpx.MockTransport(handler))

    async def unexpected_browser_fallback(url, user_agent):
        raise AssertionError("500 responses must not trigger Chromium fallback")

    monkeypatch.setattr(service, "_check_browser_url", unexpected_browser_fallback)
    result = await service.check(
        RedirectCheckRequest(mode="urls", urls=["https://example.com/page"])
    )

    assert result.data.results[0].final_status == 500
    assert result.data.results[0].error is None


@pytest.mark.asyncio
async def test_successful_javascript_redirect_uses_browser_fallback(monkeypatch):
    async def handler(request):
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            content=b"<script>location.href='/new'</script>",
            request=request,
        )

    service = RedirectCheckerService(http_transport=httpx.MockTransport(handler))
    expected = service._failed_result(
        "https://example.com/page", [], "https://example.com/page", "browser result"
    )

    async def browser_fallback(url, user_agent):
        return expected

    monkeypatch.setattr(service, "_check_browser_url", browser_fallback)
    result = await service.check(
        RedirectCheckRequest(mode="urls", urls=["https://example.com/page"])
    )

    assert result.data.results[0].error == "browser result"


@pytest.mark.asyncio
async def test_domain_mode_reuses_crawler_and_caps_browser_checks(monkeypatch):
    crawler_calls = {}

    class FakeCrawler:
        def __init__(self, **kwargs):
            crawler_calls.update(kwargs)

        async def crawl(self):
            return SimpleNamespace(
                graph=SimpleNamespace(pages={
                    "https://example.com/": object(),
                    "https://example.com/about": object(),
                    "https://example.com/contact": object(),
                }),
                crawl_truncated=True,
            )

    service = RedirectCheckerService(site_crawler_factory=FakeCrawler)
    checked_urls = []

    async def browser_checks(urls, user_agent):
        checked_urls.extend(urls)
        return [
            service._failed_result(url, [], url, "mock result") for url in urls
        ]

    monkeypatch.setattr(service, "_check_browser_urls", browser_checks)
    result = await service.check(RedirectCheckRequest(
        mode="domain", domain="https://example.com", max_urls=2
    ))

    assert crawler_calls["canonical_url"] == "https://example.com/"
    assert crawler_calls["max_pages"] == 2
    assert checked_urls == ["https://example.com/", "https://example.com/about"]
    assert result.data.checked == 2
    assert result.data.truncated == 1


@pytest.mark.asyncio
async def test_domain_mode_fails_if_crawler_processes_no_pages():
    class EmptyCrawler:
        def __init__(self, **kwargs):
            pass

        async def crawl(self):
            return SimpleNamespace(
                graph=SimpleNamespace(pages={}),
                pages_crawled=0,
                crawl_truncated=False,
            )

    service = RedirectCheckerService(site_crawler_factory=EmptyCrawler)

    with pytest.raises(RedirectCheckInfrastructureError):
        await service.check(RedirectCheckRequest(
            mode="domain", domain="https://example.com"
        ))


@pytest.mark.asyncio
async def test_browser_mode_records_main_frame_http_redirect_chain():
    class FakePage:
        main_frame = object()
        url = "https://example.com/final"

        def __init__(self):
            self.handlers = {}
            self.route = AsyncMock()
            self.goto = AsyncMock(side_effect=self._navigate)
            self.wait_for_load_state = AsyncMock()

        def on(self, event, callback):
            self.handlers[event] = callback

        async def _navigate(self, url, **kwargs):
            first = SimpleNamespace(
                frame=self.main_frame,
                url=url,
                is_navigation_request=lambda: True,
            )
            self.handlers["request"](first)
            self.handlers["response"](SimpleNamespace(
                request=first,
                url=url,
                status=301,
                status_text="Moved Permanently",
                all_headers=AsyncMock(return_value={"location": "/final"}),
            ))
            second_url = "https://example.com/final"
            second = SimpleNamespace(
                frame=self.main_frame,
                url=second_url,
                is_navigation_request=lambda: True,
            )
            self.handlers["request"](second)
            self.handlers["response"](SimpleNamespace(
                request=second,
                url=second_url,
                status=200,
                status_text="OK",
                all_headers=AsyncMock(return_value={"content-type": "text/html"}),
            ))

    page = FakePage()

    class FakePool:
        @asynccontextmanager
        async def get_page(self, config):
            yield page

    service = RedirectCheckerService(browser_pool=FakePool())
    result = await service._check_browser_url(
        "https://example.com/start", USER_AGENTS["chrome"][1]
    )

    assert result.redirects == 1
    assert [hop.status for hop in result.hops] == [301, 200]
    assert result.hops[0].resolved == "https://example.com/final"
    assert result.final_url == "https://example.com/final"


@pytest.mark.asyncio
async def test_redirect_without_location_is_reported():
    async def handler(request):
        return httpx.Response(301, request=request)

    service = RedirectCheckerService(http_transport=httpx.MockTransport(handler))
    result = await service.check(
        RedirectCheckRequest(mode="urls", urls=["https://example.com/old"])
    )

    assert result.data.results[0].final_status == 301
    assert result.data.results[0].error == "Redirect response did not include a Location header."


@pytest.mark.asyncio
async def test_redirect_limit_is_enforced(monkeypatch):
    monkeypatch.setattr(
        "app.modules.seprate_checks.bulk_status.service.settings.LINK_ANALYSIS_MAX_REDIRECT_HOPS",
        1,
    )

    async def handler(request):
        path = urlsplit(str(request.url)).path
        destination = "/two" if path == "/one" else "/three"
        return httpx.Response(302, headers={"location": destination}, request=request)

    service = RedirectCheckerService(http_transport=httpx.MockTransport(handler))
    result = await service.check(
        RedirectCheckRequest(mode="urls", urls=["https://example.com/one"])
    )

    assert result.data.results[0].redirects == 2
    assert result.data.results[0].error == "Maximum redirect limit exceeded."


@pytest.mark.asyncio
async def test_timeout_is_reported_without_exposing_exception_details():
    async def handler(request):
        raise httpx.ReadTimeout("sensitive network details", request=request)

    service = RedirectCheckerService(http_transport=httpx.MockTransport(handler))
    result = await service.check(
        RedirectCheckRequest(mode="urls", urls=["https://example.com/page"])
    )

    assert result.data.results[0].error == "Request timed out."


@pytest.mark.asyncio
async def test_post_queues_check_and_returns_check_and_task_ids(monkeypatch):
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/redirect-check")
    sent = {}
    stored = {}

    def fake_send_task(name, args, task_id, queue):
        sent.update(name=name, args=args, task_id=task_id, queue=queue)
        return SimpleNamespace(id=task_id)

    fake_celery = SimpleNamespace(
        backend=SimpleNamespace(
            store_result=lambda *args: stored.update(args=args),
            forget=lambda *args: None,
        ),
        send_task=fake_send_task,
    )
    monkeypatch.setattr(
        "app.modules.seprate_checks.bulk_status.router.celery_app", fake_celery
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/redirect-check/check",
            json={"mode": "urls", "urls": ["https://example.com/old"]},
        )

    assert response.status_code == 202
    payload = response.json()
    assert payload["check_id"] == payload["task_id"]
    assert payload["status"] == "queued"
    assert payload["status_url"] == f"/api/v1/redirect-check/check/{payload['check_id']}"
    assert sent["name"] == "redirect_check.run_check"
    assert sent["queue"] == "crawler"
    assert sent["task_id"] == payload["check_id"]
    assert stored["args"][2] == "QUEUED"


@pytest.mark.asyncio
async def test_poll_returns_task_status_and_result_in_sample_format(monkeypatch):
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/redirect-check")
    check_id = "3bbd47f4-7ae7-4bd2-aaba-1d6173f60b0a"
    final_result = {
        "data": {
            "results": [{
                "input": "https://example.com/old",
                "hops": [],
                "redirects": 0,
                "finalUrl": "https://example.com/old",
                "finalStatus": 200,
                "error": None,
            }],
            "checked": 1,
            "truncated": 0,
            "maxUrls": 25,
            "userAgent": {"key": "chrome", "label": "Desktop Chrome"},
        },
        "cost": 0.25,
    }

    fake_celery = SimpleNamespace(
        AsyncResult=lambda task_id: SimpleNamespace(state="SUCCESS", result=final_result)
    )
    monkeypatch.setattr(
        "app.modules.seprate_checks.bulk_status.router.celery_app", fake_celery
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(f"/api/v1/redirect-check/check/{check_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["check_id"] == check_id
    assert payload["task_id"] == check_id
    assert payload["result"] == final_result


@pytest.mark.asyncio
async def test_poll_reports_running_state(monkeypatch):
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/redirect-check")
    check_id = "3bbd47f4-7ae7-4bd2-aaba-1d6173f60b0a"
    fake_celery = SimpleNamespace(
        AsyncResult=lambda task_id: SimpleNamespace(state="STARTED", result=None)
    )
    monkeypatch.setattr(
        "app.modules.seprate_checks.bulk_status.router.celery_app", fake_celery
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(f"/api/v1/redirect-check/check/{check_id}")

    assert response.status_code == 200
    assert response.json()["status"] == "running"
