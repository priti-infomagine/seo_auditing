"""Unit tests for the SERP DataForSEO client.

Mirrors the style of ``backlink_analysis/tests/test_data_for_seo_client.py``:
the httpx transport is faked by replacing ``_get_client``.

These focus on the location targeting contract: ``location_code`` and
``location_name`` are mutually exclusive, and ``location_code`` takes
precedence when both are present.
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest

from app.modules.separate_checks.serp_rank_check.client import (
    SERPDataForSEOClient,
)


def _resp(body, status_code=200):
    return httpx.Response(
        status_code,
        json=body,
        request=httpx.Request("POST", "https://api.dataforseo.com/v3"),
    )


@pytest.fixture
def fake_http():
    client = SERPDataForSEOClient("login", "password")
    http_client = AsyncMock()
    http_client.post = AsyncMock(return_value=_resp({"status_code": 20000, "tasks": []}))
    http_client.get = AsyncMock(return_value=_resp({"status_code": 20000, "tasks": []}))
    # _get_client normally checks is_closed; we bypass it entirely.
    client._get_client = lambda: http_client
    return client, http_client


@pytest.mark.asyncio
async def test_organic_sends_location_code_not_name_when_code_provided(fake_http):
    client, http_client = fake_http

    await client.serp_google_organic_live_advanced(
        keyword="seo",
        location_name="United States",
        location_code=1007805,
        language_name="English",
        device="desktop",
        depth=10,
    )
    payload = http_client.post.await_args.kwargs["json"][0]
    assert payload["location_code"] == 1007805
    # Never send both.
    assert "location_name" not in payload


@pytest.mark.asyncio
async def test_organic_sends_location_name_when_no_code(fake_http):
    client, http_client = fake_http

    await client.serp_google_organic_live_advanced(
        keyword="seo",
        location_name="United States",
        language_name="English",
        device="desktop",
        depth=10,
    )
    payload = http_client.post.await_args.kwargs["json"][0]
    assert payload["location_name"] == "United States"
    assert "location_code" not in payload


@pytest.mark.asyncio
async def test_locations_get_uses_country_path(fake_http):
    client, http_client = fake_http

    await client.serp_google_locations(country="in")
    assert http_client.get.await_args.args[0] == (
        "https://api.dataforseo.com/v3/serp/google/locations/in"
    )


@pytest.mark.asyncio
async def test_locations_get_no_country_uses_base_path(fake_http):
    client, http_client = fake_http

    await client.serp_google_locations()
    assert http_client.get.await_args.args[0] == (
        "https://api.dataforseo.com/v3/serp/google/locations"
    )
