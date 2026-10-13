"""FastAPI routes for the SERP rank check module.

The API never calls the DataForSEO provider directly —
every provider call happens inside the ``run_serp_check``
Celery task. The API only validates, inserts the queued
row and enqueues the task.
"""
from __future__ import annotations

import asyncio
from typing import Optional
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Response,
    status,
)
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.logger import logger
from app.modules.auth.models.users import User
from app.core.security import get_current_user
from app.shared.tasks.celery_app import celery_app

from .model import RankCheck
from .preview import PreviewStorage
from .repository import (
    RankCheckRepository,
    SerpLanguageRepository,
    SerpLocationRepository,
)
from .schema import (
    RankCheckCreateResponse,
    RankCheckListResponse,
    RankCheckRequest,
    RankCheckStatusResponse,
    RankCheckResult,
    SerpLanguageListResponse,
    SerpLanguageResponse,
    SerpLocationListResponse,
    SerpLocationResponse,
)
from .service import SerpRankCheckService

router = APIRouter()


def _to_status_response(check: RankCheck) -> RankCheckStatusResponse:
    result = None
    if check.result:
        result = RankCheckResult(**check.result)
    return RankCheckStatusResponse(
        id=check.id,
        keyword=check.keyword,
        domain=check.domain,
        location_code=check.location_code,
        language_code=check.language_code,
        device=check.device,
        depth=check.depth,
        include_preview=check.include_preview,
        status=check.status,
        result=result,
        preview_status=check.preview_status,
        preview_html_url=check.preview_html_url,
        preview_image_url=check.preview_image_url,
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


@router.get(
    "/locations",
    response_model=SerpLocationListResponse,
    summary="List available SERP locations",
)
async def list_locations(
    q: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SerpLocationListResponse:
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    loc_repo = SerpLocationRepository(db)
    locations = await loc_repo.list(q, limit, offset)
    total = await loc_repo.count(q)
    return SerpLocationListResponse(
        items=[
            SerpLocationResponse(
                location_code=loc.location_code,
                name=loc.name,
                country_iso=loc.country_iso,
                location_type=loc.location_type,
            )
            for loc in locations
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/languages",
    response_model=SerpLanguageListResponse,
    summary="List available SERP languages",
)
async def list_languages(
    limit: int = 200,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SerpLanguageListResponse:
    limit = max(1, min(limit, 500))
    offset = max(0, offset)
    lang_repo = SerpLanguageRepository(db)
    languages = await lang_repo.list(limit, offset)
    total = await lang_repo.count()
    return SerpLanguageListResponse(
        items=[
            SerpLanguageResponse(
                language_code=lang.language_code,
                name=lang.name,
            )
            for lang in languages
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/rank-checks",
    response_model=RankCheckCreateResponse,
    summary="Queue a SERP rank check",
)
async def create_rank_check(
    body: RankCheckRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RankCheckCreateResponse:
    try:
        service = SerpRankCheckService(db)
        check, created = await service.prepare_check(
            user_id=user.id,
            keyword=body.keyword,
            domain=body.domain,
            location_code=body.location_code,
            language_code=body.language_code,
            device=body.device,
            depth=body.depth,
            include_preview=body.include_preview,
        )
        if created:
            response.status_code = status.HTTP_202_ACCEPTED
            await asyncio.to_thread(
                celery_app.send_task,
                "serp_rank_check.run_serp_check",
                args=[str(check.id)],
                queue="serp_io",
            )
        else:
            # Duplicate in-flight request — return the
            # existing job id without re-enqueueing.
            response.status_code = status.HTTP_200_OK
        return RankCheckCreateResponse(
            id=check.id, status=check.status
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.error(
            "create_rank_check: failed to queue check: %s",
            exc,
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to queue rank check",
        ) from exc


@router.get(
    "/rank-checks/{check_id}",
    response_model=RankCheckStatusResponse,
    summary="Get a rank check by id",
)
async def get_rank_check(
    check_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RankCheckStatusResponse:
    check_uuid = _parse_check_id(check_id)
    check = await RankCheckRepository(db).get_by_user(
        check_uuid, user.id
    )
    if check is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rank check with ID '{check_id}' not found",
        )
    return _to_status_response(check)


@router.get(
    "/rank-checks",
    response_model=RankCheckListResponse,
    summary="List rank check history for the current user",
)
async def list_rank_checks(
    limit: int = 20,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RankCheckListResponse:
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    checks, total = await RankCheckRepository(db).list_for_user(
        user.id, limit, offset
    )
    return RankCheckListResponse(
        items=[_to_status_response(check) for check in checks],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/previews/{check_id}/{filename}")
async def get_preview_artifact(
    check_id: str,
    filename: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FileResponse:
    """Serve a stored preview artifact (HTML or screenshot)."""
    check_uuid = _parse_check_id(check_id)
    check = await RankCheckRepository(db).get_by_user(
        check_uuid, user.id
    )
    if check is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Preview not found",
        )
    storage = PreviewStorage()
    path = storage.resolve(check_uuid, filename)
    if path is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Preview artifact not found",
        )
    media_type = (
        "text/html" if filename == "preview.html" else "image/png"
    )
    return FileResponse(path, media_type=media_type)
