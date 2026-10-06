from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.logger import logger

from .model import BacklinkCheck, BacklinkCheckStatus
from .repository import BacklinkCheckRepository
from .schema import (
    BacklinkCheckListResponse,
    BacklinkCheckRequest,
    BacklinkCheckResponse,
    BacklinkEvidence,
    BacklinkMetrics,
    BacklinkReportItem,
)
from .service import BacklinkAnalysisService, DataForSEOConfigurationError
from app.modules.seprate_checks.meta_check.validation import normalize_target_url

router = APIRouter()


def _to_response(check: BacklinkCheck) -> BacklinkCheckResponse:
    return BacklinkCheckResponse(
        check_id=check.id,
        target=check.target,
        status=BacklinkCheckStatus(check.status),
        result=[
            BacklinkReportItem(
                data=BacklinkMetrics(**item["data"]),
                cost=item["cost"],
                evidence=BacklinkEvidence(**item["evidence"]),
            )
            for item in (check.result or [])
        ],
        cost=check.cost,
        error=check.error,
        created_at=check.created_at.isoformat() if check.created_at else None,
        updated_at=check.updated_at.isoformat() if check.updated_at else None,
    )


async def _get_check(check_id: str, db: AsyncSession) -> BacklinkCheck:
    try:
        parsed_id = UUID(check_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid check ID format (must be a valid UUID)",
        ) from exc

    check = await BacklinkCheckRepository(db).get(parsed_id)
    if check is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Backlink check with ID '{check_id}' not found",
        )
    return check


@router.post(
    "/check",
    response_model=list[BacklinkReportItem],
    status_code=status.HTTP_201_CREATED,
    summary="Run and save a backlink analysis",
)
async def check_backlinks(
    body: BacklinkCheckRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> list[BacklinkReportItem]:
    try:
        check = await BacklinkAnalysisService.run_check(
            body.target,
            body.evidence_limit,
            db,
        )
        response.headers["Location"] = f"/api/v1/backlinks/checks/{check.id}"
        return _to_response(check).result
    except DataForSEOConfigurationError as exc:
        logger.error("check_backlinks: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Backlink analysis provider is not configured",
        ) from exc
    except (httpx.HTTPError, RuntimeError, ValueError) as exc:
        logger.error("check_backlinks: DataForSEO request failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Backlink analysis provider request failed",
        ) from exc


@router.get(
    "/checks",
    response_model=BacklinkCheckListResponse,
    summary="List saved backlink analyses",
)
async def list_backlink_checks(
    target: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> BacklinkCheckListResponse:
    normalized_target = None
    if target is not None:
        try:
            _, normalized_target = normalize_target_url(target)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            ) from exc
    checks, total = await BacklinkCheckRepository(db).list(
        normalized_target,
        limit,
        offset,
    )
    return BacklinkCheckListResponse(
        items=[_to_response(check) for check in checks],
        total=total,
    )


@router.get(
    "/checks/{check_id}",
    response_model=BacklinkCheckResponse,
    summary="Retrieve a saved backlink analysis",
)
async def get_backlink_check(
    check_id: str,
    db: AsyncSession = Depends(get_db),
) -> BacklinkCheckResponse:
    check = await _get_check(check_id, db)
    return _to_response(check)
