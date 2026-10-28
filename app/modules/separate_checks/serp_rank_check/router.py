"""FastAPI routes for the SERP rank check module.

The API endpoint calls DataForSEO directly (synchronous flow):
validate → call provider → parse → persist → return.
"""
from __future__ import annotations

import time
from typing import Any
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.logger import logger

from .client import (
    SERPDataForSEOConfigurationError,
    get_serp_client,
)
from .exceptions import (
    SerpProvider4xx,
    SerpProvider5xx,
    SerpProviderTimeout,
)
from .model import RankCheck
from .repository import RankCheckRepository
from .schema import (
    LocationOption,
    RankCheckListResponse,
    RankCheckRequest,
    RankCheckResult,
    RankCheckStatusResponse,
)
from .service import SerpRankCheckService

router = APIRouter()


# ── In-memory cache for the locations list ────────────────────
# The DataForSEO locations list changes very rarely (geographic
# boundaries are stable), so caching per-country for ~24h avoids
# re-fetching on every keystroke.  This mirrors the module-level
# singleton pattern used by ``get_serp_client``.  A ``None`` key
# represents the "all countries" fetch (``/serp/google/locations``).

_LOCATIONS_CACHE_TTL_SECONDS: float = 24 * 60 * 60
_locations_cache: dict[str | None, tuple[float, list[dict[str, Any]]]] = {}


def _locations_expired(entry: tuple[float, list[dict[str, Any]]]) -> bool:
    expires_at, _ = entry
    return time.monotonic() >= expires_at


def _to_status_response(check: RankCheck) -> RankCheckStatusResponse:
    result = None
    if check.result:
        result = RankCheckResult(**check.result)
    return RankCheckStatusResponse(
        id=check.id,
        keyword=check.keyword,
        domain=check.domain,
        location=(check.location_name or ""),
        location_code=check.location_code,
        language=(check.language_name or ""),
        device=check.device,
        depth=check.depth,
        deep_tracking=check.deep_tracking,
        status=check.status,
        result=result,
        error_code=check.error_code,
        provider_cost=(
            float(check.provider_cost)
            if check.provider_cost is not None
            else None
        ),
        created_at=(
            check.created_at.isoformat()
            if check.created_at
            else None
        ),
        updated_at=(
            check.updated_at.isoformat()
            if check.updated_at
            else None
        ),
    )


def _parse_check_id(check_id: str) -> UUID:
    try:
        return UUID(check_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid check ID format (must be a valid UUID)",
        ) from exc


@router.post(
    "/rank-checks",
    response_model=RankCheckStatusResponse,
    summary="Perform a SERP rank check",
)
async def create_rank_check(
    body: RankCheckRequest,
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> RankCheckStatusResponse:
    """Validate input, call DataForSEO, calculate ranking, persist, and return.

    The endpoint blocks until the DataForSEO provider responds.
    """
    try:
        service = SerpRankCheckService(db)
        deep_tracking = body.domain is not None
        check, _ = await service.check_serp_rank(
            user_id=None,
            keyword=body.keyword,
            domain=body.domain,
            location_name=body.location,
            location_code=body.location_code,
            language_name=body.language,
            device=body.device,
            depth=body.depth,
            deep_tracking=deep_tracking,
        )
        await db.refresh(check)
        return _to_status_response(check)
    except SerpProviderTimeout as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=str(exc),
        ) from exc
    except SerpProvider4xx as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    except SerpProvider5xx as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.error(
            "create_rank_check: failed: %s", exc, exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to complete rank check",
        ) from exc


@router.get(
    "/rank-checks/{check_id}",
    response_model=RankCheckStatusResponse,
    summary="Get a rank check by id",
)
async def get_rank_check(
    check_id: str,
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> RankCheckStatusResponse:
    check_uuid = _parse_check_id(check_id)
    check = await RankCheckRepository(db).get(check_uuid)
    if check is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rank check with ID '{check_id}' not found",
        )
    return _to_status_response(check)


@router.get(
    "/rank-checks",
    response_model=RankCheckListResponse,
    summary="List all rank checks",
)
async def list_rank_checks(
    limit: int = 20,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> RankCheckListResponse:
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    checks, total = await RankCheckRepository(db).list_all(
        limit, offset
    )
    return RankCheckListResponse(
        items=[_to_status_response(check) for check in checks],
        total=total,
        limit=limit,
        offset=offset,
    )


# ── Location autocomplete ──────────────────────────────────


async def _fetch_locations_cached(
    country: str | None,
) -> list[dict[str, Any]]:
    """Return the DataForSEO Google location list for *country*.

    The full list is fetched once per (country, process) and cached
    for ``_LOCATIONS_CACHE_TTL_SECONDS`` so the provider is not hit on
    every keystroke.  ``country=None`` fetches the global list
    (``/serp/google/locations``); a value such as ``"in"`` fetches the
    country-scoped list (``/serp/google/locations/in``).

    Raises ``SerpProvider4xx``/``SerpProvider5xx``/
    ``SerpProviderTimeout``/``SERPDataForSEOConfigurationError`` on
    failure — the endpoint maps these to HTTP statuses.
    """
    cache_key = country
    cached = _locations_cache.get(cache_key)
    if cached is not None and not _locations_expired(cached):
        _, items = cached
        return items

    client = await get_serp_client()
    body = await client.serp_google_locations(country=country)
    # Body shape: {status_code, tasks: [{result: [location, ...]}]}
    items: list[dict[str, Any]] = []
    tasks = body.get("tasks")
    if isinstance(tasks, list) and tasks and isinstance(tasks[0], dict):
        result = tasks[0].get("result")
        if isinstance(result, list):
            items = [item for item in result if isinstance(item, dict)]

    _locations_cache[cache_key] = (
        time.monotonic() + _LOCATIONS_CACHE_TTL_SECONDS,
        items,
    )
    logger.info(
        "serp_rank_check.locations: cached %d locations for country=%s",
        len(items),
        country,
    )
    return items


def _filter_and_rank_locations(
    items: list[dict[str, Any]], query: str
) -> list[dict[str, Any]]:
    """Case-insensitive name match, City-first, limited to 10.

    Sorting City-level locations first ensures the most granular match
    is surfaced first, which is what disambiguates same-name locations
    (e.g. a City "Jaipur" vs. a Sub District "Jaipur") when the caller
    resolves them by ``location_code``.
    """
    q = (query or "").strip().lower()
    if not q:
        return []
    matched = [
        item
        for item in items
        if q in (item.get("location_name") or "").lower()
    ]
    matched.sort(
        key=lambda item: (
            0 if (item.get("location_type") or "") == "City" else 1,
            item.get("location_name") or "",
        )
    )
    return matched[:10]


@router.get(
    "/locations",
    response_model=list[LocationOption],
    summary="Search DataForSEO Google locations",
    openapi_extra={
        "description": (
            "Autocomplete endpoint for Google target locations. "
            "The location list is fetched from DataForSEO using the "
            "backend's Basic-auth credentials (never from the browser) "
            "and cached in memory for ~24h. Matches are case-insensitive "
            "on location_name, City results are sorted first, and the "
            "list is capped at 10."
        ),
    },
)
async def search_locations(
    q: str = Query(default="", max_length=200),
    country: str | None = Query(default=None, max_length=2),
) -> list[LocationOption]:
    """Search Google target locations by name.

    ``q`` is matched case-insensitively against ``location_name``.
    ``country`` scopes the fetch to an ISO country code (e.g. ``"in"``)
    and caches that slice separately from the global list.
    """
    try:
        items = await _fetch_locations_cached(country)
    except SERPDataForSEOConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Location provider is not configured",
        ) from exc
    except SerpProviderTimeout as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=str(exc),
        ) from exc
    except (SerpProvider4xx, SerpProvider5xx) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    filtered = _filter_and_rank_locations(items, q)
    return [
        LocationOption(
            code=item["location_code"],
            name=item["location_name"],
            type=item.get("location_type"),
        )
        for item in filtered
        if isinstance(item.get("location_code"), int)
        and isinstance(item.get("location_name"), str)
    ]
