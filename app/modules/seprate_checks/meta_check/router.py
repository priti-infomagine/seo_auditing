import asyncio
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.logger import logger
from app.shared.tasks.celery_app import celery_app

from .model import MetaCheck, MetaCheckStatus
from .repository import MetaCheckRepository
from .schema import (
    MetaCheckRequest,
    MetaCheckQueuedResponse,
    MetaCheckResultResponse,
    MetaCheckStatusResponse,
    MetaFinding,
    MetaPageResult,
    MetaSummary,
)
from .service import MetaCheckService

router = APIRouter()


def _status(value) -> MetaCheckStatus:
    return value if isinstance(value, MetaCheckStatus) else MetaCheckStatus(value)


def _to_result_response(check: MetaCheck) -> MetaCheckResultResponse:
    return MetaCheckResultResponse(
        check_id=check.id,
        url=check.url,
        domain=check.domain,
        status=_status(check.status),
        progress=check.progress,
        error=check.error,
        checked_at=check.updated_at.isoformat() if check.updated_at else None,
        overall_status=check.overall_status,
        severity=check.severity,
        summary=MetaSummary(**(check.summary or {})),
        pages=[MetaPageResult(**page) for page in (check.pages or [])],
        findings=[MetaFinding(**finding) for finding in (check.findings or [])],
        cost_seconds=check.cost_seconds,
    )


async def _get_check(check_id: str, db: AsyncSession) -> MetaCheck:
    try:
        parsed_id = UUID(check_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid check ID format (must be a valid UUID)",
        ) from exc

    check = await MetaCheckRepository(db).get(parsed_id)
    if check is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Meta check with ID '{check_id}' not found",
        )
    return check


@router.post(
    "/check",
    response_model=MetaCheckQueuedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Queue a multi-page meta title and description check",
)
async def check_meta(
    body: MetaCheckRequest,
    db: AsyncSession = Depends(get_db),
) -> MetaCheckQueuedResponse:
    try:
        check = await MetaCheckService.prepare_check(body, db)
        task = await asyncio.to_thread(
            celery_app.send_task,
            "meta.run_check",
            args=[str(check.id)],
            queue="crawler",
        )
        check.task_id = task.id
        await db.commit()
        return MetaCheckQueuedResponse(
            check_id=check.id,
            task_id=task.id,
            url=check.url,
            domain=check.domain,
            status=_status(check.status),
            max_pages=check.max_pages,
            max_depth=check.max_depth,
            created_at=check.created_at.isoformat() if check.created_at else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("check_meta: failed to queue check: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to queue metadata check",
        ) from exc


@router.get(
    "/status/{check_id}",
    response_model=MetaCheckStatusResponse,
    summary="Poll metadata check progress",
)
async def get_meta_status(
    check_id: str,
    db: AsyncSession = Depends(get_db),
) -> MetaCheckStatusResponse:
    check = await _get_check(check_id, db)
    return MetaCheckStatusResponse(
        check_id=check.id,
        url=check.url,
        domain=check.domain,
        status=_status(check.status),
        progress=check.progress,
        error=check.error,
    )


@router.get(
    "/result/{check_id}",
    response_model=MetaCheckResultResponse,
    summary="Retrieve metadata check results",
)
async def get_meta_result(
    check_id: str,
    db: AsyncSession = Depends(get_db),
) -> MetaCheckResultResponse:
    check = await _get_check(check_id, db)
    return _to_result_response(check)