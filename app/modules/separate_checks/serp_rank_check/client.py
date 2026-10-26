"""Dedicated DataForSEO client for the SERP rank-check module.

This is intentionally kept separate from the backlink-analysis
client so that SERP-specific request/response shapes do not
bleed into backlink code and vice-versa.

Key differences from ``backlink_analysis.data_for_seo_client``:

* Accepts ``location_name`` and ``language_name`` **strings**
  (e.g. ``"United States"``, ``"English"``) directly — no
  integer ``location_code`` / ``language_code`` lookup is needed.
* Raises typed exceptions (``SerpProvider4xx``, ``SerpProvider5xx``,
  ``SerpProviderTimeout``) so the caller can classify errors and
  decide on retry behaviour.  An empty response body is **not**
  treated as an error — it simply means "no results for this
  keyword", which is a successful (not failed) outcome.
"""
from __future__ import annotations

import base64
from typing import Any

import httpx

from app.core.config import settings

from .exceptions import (
    SerpProvider4xx,
    SerpProvider5xx,
    SerpProviderTimeout,
)

RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class SERPDataForSEOConfigurationError(RuntimeError):
    """DataForSEO credentials are missing."""


class SERPDataForSEOClient:
    """Async client for the DataForSEO Google Organic Live Advanced API.

    A single instance owns one reusable ``httpx.AsyncClient``
    connection pool.  Call ``aclose()`` during application shutdown
    to release the pool cleanly.
    """

    BASE_URL = "https://api.dataforseo.com/v3"

    def __init__(
        self,
        login: str,
        password: str,
        timeout: float = 30.0,
        max_attempts: int = 3,
    ):
        token = base64.b64encode(
            f"{login}:{password}".encode()
        ).decode()
        self._headers = {
            "Authorization": f"Basic {token}",
            "Content-Type": "application/json",
        }
        self._timeout = timeout
        self._max_attempts = max_attempts
        self._client: httpx.AsyncClient | None = None

    # ── connection-pool management ─────────────────────────

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=self._timeout,
                headers=self._headers,
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
        self._client = None

    # ── API methods ─────────────────────────────────────────

    async def serp_google_organic_live_advanced(
        self,
        *,
        keyword: str,
        location_name: str,
        language_name: str,
        device: str,
        depth: int,
        find_targets_in: list[str] | None = None,
        stop_crawl_on_match: list[dict[str, str]] | None = None,
        target_search_mode: str | None = None,
    ) -> dict[str, Any]:
        """Call the Google Organic Live Advanced endpoint.

        Returns the raw response body (a dict with ``status_code``,
        ``tasks``, ``cost`` etc.).  The caller is responsible for
        validating the body's ``status_code`` and extracting results.

        When ``stop_crawl_on_match`` is provided, DataForSEO stops
        crawling once a matching URL is found, returning results up
        to and including that match.  ``find_targets_in`` restricts
        which SERP element types are checked for the match (e.g.
        ``["organic"]``).  These parameters are optional and only sent
        when provided.

        Raises ``SerpProviderTimeout`` on transport / timeout errors
        and ``SerpProvider4xx`` / ``SerpProvider5xx`` on HTTP status
        errors.
        """
        task: dict[str, Any] = {
            "keyword": keyword,
            "location_name": location_name,
            "language_name": language_name,
            "device": device,
            "depth": depth,
        }
        if find_targets_in is not None:
            task["find_targets_in"] = find_targets_in
        if stop_crawl_on_match is not None:
            task["stop_crawl_on_match"] = stop_crawl_on_match
        if target_search_mode is not None:
            task["target_search_mode"] = target_search_mode
        payload = [task]
        return await self._post_with_retries(
            "/serp/google/organic/live/advanced", payload
        )

    # ── internals ───────────────────────────────────────────

    async def _post_with_retries(
        self,
        endpoint: str,
        payload: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """POST with retry-on-transient.

        Non-retryable HTTP errors (4xx) and exhausted retries
        propagate as typed exceptions that the service layer
        can classify.
        """
        import asyncio

        last_exc: Exception | None = None
        for attempt in range(1, self._max_attempts + 1):
            try:
                client = self._get_client()
                response = await client.post(
                    f"{self.BASE_URL}{endpoint}",
                    json=payload,
                )
                if (
                    response.status_code in RETRYABLE_STATUS
                    and attempt < self._max_attempts
                ):
                    await asyncio.sleep(2 ** (attempt - 1))
                    continue
                response.raise_for_status()
                body = response.json()
                if not isinstance(body, dict):
                    raise TypeError(
                        "DataForSEO returned a non-object JSON response"
                    )
                return body
            except httpx.TimeoutException as exc:
                last_exc = exc
                if attempt < self._max_attempts:
                    await asyncio.sleep(2 ** (attempt - 1))
                    continue
                raise SerpProviderTimeout(
                    f"DataForSEO timeout: {exc}"
                ) from exc
            except httpx.TransportError as exc:
                last_exc = exc
                if attempt < self._max_attempts:
                    await asyncio.sleep(2 ** (attempt - 1))
                    continue
                raise SerpProviderTimeout(
                    f"DataForSEO connection error: {exc}"
                ) from exc
            except httpx.HTTPStatusError as exc:
                status_code = (
                    exc.response.status_code if exc.response else 0
                )
                # Include the response body in the error message
                # so callers can see DataForSEO's status_message.
                detail = ""
                if exc.response is not None:
                    try:
                        err_body = exc.response.json()
                        if isinstance(err_body, dict):
                            msg = err_body.get("status_message", "")
                            if msg:
                                detail = f": {msg}"
                    except Exception:  # noqa: BLE001
                        detail = ""
                if (
                    status_code in RETRYABLE_STATUS
                    and attempt < self._max_attempts
                ):
                    await asyncio.sleep(2 ** (attempt - 1))
                    continue
                if 500 <= status_code < 600:
                    raise SerpProvider5xx(
                        f"DataForSEO HTTP {status_code}{detail}"
                    ) from exc
                raise SerpProvider4xx(
                    f"DataForSEO HTTP {status_code}{detail}"
                ) from exc
        if last_exc is not None:
            raise SerpProviderTimeout(str(last_exc)) from last_exc
        raise SerpProvider5xx("DataForSEO request exhausted retries")


# ── Module-level singleton ──────────────────────────────────
# Mirrors the pattern used by backlink_analysis.service so that
# the connection pool is created once and reused across requests.

_client: SERPDataForSEOClient | None = None
_credentials: tuple[str, str] | None = None


async def get_serp_client() -> SERPDataForSEOClient:
    """Return the shared SERPDataForSEOClient singleton.

    The singleton is recreated only when the credentials change,
    so a credential rotation mid-process is handled correctly.
    """
    global _client, _credentials
    if not settings.DATAFORSEO_LOGIN or not settings.DATAFORSEO_PASSWORD:
        raise SERPDataForSEOConfigurationError(
            "DataForSEO credentials are not configured"
        )
    credentials = (settings.DATAFORSEO_LOGIN, settings.DATAFORSEO_PASSWORD)
    if _credentials != credentials:
        if _client is not None:
            await _client.aclose()
        _client = SERPDataForSEOClient(
            settings.DATAFORSEO_LOGIN,
            settings.DATAFORSEO_PASSWORD,
            timeout=settings.SERP_PROVIDER_TIMEOUT,
            max_attempts=3,
        )
        _credentials = credentials
    return _client


async def close_serp_client() -> None:
    """Close the shared client (call during app shutdown)."""
    global _client, _credentials
    if _client is not None:
        await _client.aclose()
    _client = None
    _credentials = None
