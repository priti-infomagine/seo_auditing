"""FastAPI routes for the SERP rank check module.

The API endpoint calls DataForSEO directly (synchronous flow):
validate → call provider → parse → persist → return.

Preview generation is still asynchronous via Celery.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.logger import logger

from .exceptions import (
    SerpProvider4xx,
    SerpProvider5xx,
    SerpProviderTimeout,
)
from .model import RankCheck
from .preview import PreviewStorage
from .repository import RankCheckRepository
from .schema import (
    RankCheckListResponse,
    RankCheckRequest,
    RankCheckResult,
    RankCheckStatusResponse,
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
        location=check.location_name,
        language=check.language_name,
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
    If ``include_preview`` is true, a preview task is enqueued
    asynchronously after the ranking is stored.
    """
    try:
        service = SerpRankCheckService(db)
        check, _ = await service.check_serp_rank(
            user_id=None,
            keyword=body.keyword,
            domain=body.domain,
            location_name=body.location,
            language_name=body.language,
            device=body.device,
            depth=body.depth,
            include_preview=body.include_preview,
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


@router.get("/previews/{check_id}/{filename}")
async def get_preview_artifact(
    check_id: str,
    filename: str,
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> FileResponse:
    """Serve a stored preview artifact (HTML or screenshot)."""
    check_uuid = _parse_check_id(check_id)
    check = await RankCheckRepository(db).get(check_uuid)
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
