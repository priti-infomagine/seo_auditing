from unittest.mock import AsyncMock

import httpx
import pytest

from app.modules.seprate_checks.backlink_analysis.data_for_seo_client import (
    DataForSEOClient,
    normalize_domain,
)


def response(body, status_code=200):
    return httpx.Response(
        status_code,
        json=body,
        request=httpx.Request("POST", "https://api.dataforseo.com/v3"),
    )


def summary_response(*, broken_backlinks=2, cost=0.01):
    result = {
        "target": "infomagine.in",
        "rank": 108,
        "backlinks": 139,
        "referring_domains": 58,
        "referring_main_domains": 57,
        "broken_backlinks": broken_backlinks,
        "referring_pages": 96,
        "backlinks_spam_score": 12,
    }
    return response(
        {
            "status_code": 20000,
            "cost": cost,
            "tasks": [{"status_code": 20000, "result": [result]}],
        }
    )


def evidence_response(items, cost=0.001):
    return response(
        {
            "status_code": 20000,
            "cost": cost,
            "tasks": [
                {
                    "status_code": 20000,
                    "result": [{"items": items}],
                }
            ],
        }
    )


@pytest.mark.asyncio
async def test_get_backlink_summary_returns_up_to_five_urls_per_evidence_field(
    monkeypatch,
):
    client = DataForSEOClient("login", "password")
    http_client = type("HttpClient", (), {})()
    referring_urls = [f"https://source{i}.example/page" for i in range(1, 8)]
    broken_urls = [f"https://broken{i}.example/page" for i in range(1, 8)]
    http_client.post = AsyncMock(
        side_effect=[
            summary_response(),
            evidence_response(
                [{"url_from": url, "is_broken": False} for url in referring_urls]
            ),
            evidence_response(
                [{"url_from": url, "is_broken": True} for url in broken_urls]
            ),
        ]
    )
    monkeypatch.setattr(client, "_get_client", lambda: http_client)

    report = await client.get_backlink_summary(
        "https://www.infomagine.in/page"
    )

    assert report == {
        "domain": "infomagine.in",
        "domainRank": 108,
        "backlinks": 139,
        "referringDomains": 58,
        "referringMainDomains": 57,
        "referringPages": 96,
        "brokenBacklinks": 2,
        "backlinksSpamScore": 12,
        "cost": 0.012,
        "evidence": {
            "referringPages": referring_urls[:5],
            "brokenBacklinks": broken_urls[:5],
        },
    }
    assert http_client.post.await_args_list[0].args == (
        f"{client.BASE_URL}/backlinks/summary/live",
    )
    assert http_client.post.await_args_list[0].kwargs["json"] == [
        {
            "target": "infomagine.in",
            "include_subdomains": True,
            "exclude_internal_backlinks": True,
            "backlinks_status_type": "live",
        }
    ]
    assert http_client.post.await_args_list[1].kwargs["json"] == [
        {"target": "infomagine.in", "limit": 5, "mode": "as_is"}
    ]
    assert http_client.post.await_args_list[2].kwargs["json"] == [
        {
            "target": "infomagine.in",
            "limit": 5,
            "mode": "as_is",
            "filters": ["is_broken", "=", True],
        }
    ]
    assert http_client.post.await_count == 3


def test_normalize_domain_strips_scheme_www_port_and_path():
    assert normalize_domain(" HTTPS://WWW.Infomagine.IN:8443/page ") == "infomagine.in"
    assert normalize_domain("www.infomagine.in:8443/page") == "infomagine.in"


@pytest.mark.parametrize("domain", ["", "https://", "https://[invalid"])
def test_normalize_domain_rejects_empty_or_unparseable_input(domain):
    with pytest.raises(ValueError):
        normalize_domain(domain)


@pytest.mark.asyncio
async def test_get_backlink_summary_returns_empty_broken_evidence_when_count_is_zero(
    monkeypatch,
):
    client = DataForSEOClient("login", "password")
    http_client = type("HttpClient", (), {})()
    http_client.post = AsyncMock(
        side_effect=[
            summary_response(broken_backlinks=0),
            evidence_response([]),
        ]
    )
    monkeypatch.setattr(client, "_get_client", lambda: http_client)

    report = await client.get_backlink_summary("infomagine.in")

    assert report["evidence"] == {
        "referringPages": [],
        "brokenBacklinks": [],
    }
    assert http_client.post.await_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider_response", "error", "message"),
    [
        (
            {"status_code": 40501, "status_message": "Request rejected"},
            RuntimeError,
            "Request rejected",
        ),
        (
            {
                "status_code": 20000,
                "tasks": [
                    {"status_code": 40501, "status_message": "Invalid target"}
                ],
            },
            RuntimeError,
            "Invalid target",
        ),
        (
            {"status_code": 20000, "tasks": [{"status_code": 20000, "result": []}]},
            ValueError,
            "no result",
        ),
    ],
)
async def test_get_backlink_summary_validates_provider_response(
    monkeypatch,
    provider_response,
    error,
    message,
):
    client = DataForSEOClient("login", "password")
    http_client = type("HttpClient", (), {})()
    http_client.post = AsyncMock(return_value=response(provider_response))
    monkeypatch.setattr(client, "_get_client", lambda: http_client)

    with pytest.raises(error, match=message):
        await client.get_backlink_summary("example.com")


@pytest.mark.asyncio
async def test_get_backlink_summary_retries_provider_statuses_with_one_and_two_seconds(
    monkeypatch,
):
    client = DataForSEOClient("login", "password")
    http_client = type("HttpClient", (), {})()
    http_client.post = AsyncMock(
        side_effect=[
            response({}, status_code=429),
            response({}, status_code=503),
            summary_response(broken_backlinks=0),
            evidence_response([]),
        ]
    )
    sleeps = AsyncMock()
    monkeypatch.setattr(client, "_get_client", lambda: http_client)
    monkeypatch.setattr(
        "app.modules.seprate_checks.backlink_analysis.data_for_seo_client.asyncio.sleep",
        sleeps,
    )

    await client.get_backlink_summary("infomagine.in")

    assert http_client.post.await_count == 4
    assert [call.args[0] for call in sleeps.await_args_list] == [1, 2]


@pytest.mark.asyncio
async def test_get_backlink_summary_retries_transport_errors(monkeypatch):
    request = httpx.Request("POST", "https://api.dataforseo.com/v3")
    client = DataForSEOClient("login", "password")
    http_client = type("HttpClient", (), {})()
    http_client.post = AsyncMock(
        side_effect=[
            httpx.ConnectError("temporary connection failure", request=request),
            httpx.ConnectError("temporary connection failure", request=request),
            summary_response(broken_backlinks=0),
            evidence_response([]),
        ]
    )
    sleeps = AsyncMock()
    monkeypatch.setattr(client, "_get_client", lambda: http_client)
    monkeypatch.setattr(
        "app.modules.seprate_checks.backlink_analysis.data_for_seo_client.asyncio.sleep",
        sleeps,
    )

    await client.get_backlink_summary("infomagine.in")

    assert http_client.post.await_count == 4
    assert [call.args[0] for call in sleeps.await_args_list] == [1, 2]


@pytest.mark.asyncio
async def test_aclose_closes_the_reused_http_client():
    client = DataForSEOClient("login", "password")
    http_client = AsyncMock()
    http_client.is_closed = False
    client._client = http_client

    await client.aclose()

    http_client.aclose.assert_awaited_once()
    assert client._client is None
