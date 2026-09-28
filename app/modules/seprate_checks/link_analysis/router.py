"""Asynchronous Link Analysis API routes with polling.

Endpoints:
- POST /check               — Queue an asynchronous link analysis (HTTP 202)
- GET  /check/{check_id}    — Poll progress and retrieve status or results

The GET endpoint returns a unified response: when queued/processing it
returns status + progress; when completed it includes findings, summary,
and overall verdict. Use query filters (category, type, severity) to
narrow the findings list and pagination to browse.
"""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.logger import logger
from app.shared.tasks.celery_app import celery_app

from .model import (
    FindingCategory,
    FindingType,
    LinkAnalysisCheckStatus,
    LinkAnalysisSeverity,
    LinkAnalysisCheck,
)
from .repository import LinkAnalysisRepository
from .schema import (
    FindingResponse,
    LinkAnalysisCheckResponse,
    LinkAnalysisQueuedResponse,
    LinkAnalysisRequest,
)
from .service import LinkAnalysisService
from redis.asyncio import Redis
from app.core.config import settings
from app.core.redis import get_redis


router = APIRouter()


def _str_status(val) -> str:
    if hasattr(val, "value"):
        return str(val.value)
    return str(val) if val is not None else ""


async def _get_check_or_404(check_id: str, db: AsyncSession) -> LinkAnalysisCheck:
    try:
        parsed_id = UUID(check_id)
    except (ValueError, AttributeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid check ID format (must be a valid UUID)",
        ) from exc

    check = await LinkAnalysisRepository(db).get(parsed_id)
    if check is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Link analysis check with ID '{check_id}' not found",
        )
    return check


@router.post(
    "/check",
    response_model=LinkAnalysisQueuedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Queue an asynchronous Link Analysis",
    description=(
        "Enqueues an asynchronous link analysis check on the `crawler` queue. "
        "Returns immediately with HTTP 202 containing the `check_id`. "
        "Poll `GET /api/v1/link-analysis/check/{check_id}` for progress and results."
    ),
)
async def check_links(
    body: LinkAnalysisRequest,
    db: AsyncSession = Depends(get_db),
    redis: Optional[Redis] = Depends(get_redis),
) -> LinkAnalysisQueuedResponse:
    try:
        check = await LinkAnalysisService.prepare_check(body.url, db, redis=redis)

        task = celery_app.send_task(
            "link_analysis.run_check",
            args=[str(check.id), check.url],
            queue="crawler",
        )
        check.task_id = task.id
        await db.commit()

        return LinkAnalysisQueuedResponse(
            check_id=check.id,
            task_id=task.id,
            url=check.url,
            domain=check.domain,
            status=check.status,
            created_at=check.created_at.isoformat() if check.created_at else None,
        )
    except ValueError as exc:
        logger.warning("check_links: validation error: %s", exc)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        logger.error("check_links: unexpected error: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while queuing the link analysis check",
        )


@router.get(
    "/check/{check_id}",
    response_model=LinkAnalysisCheckResponse,
    summary="Poll status and retrieve results for a link analysis check",
    description=(
        "Poll this endpoint to check if the job is queued, processing, completed, "
        "or failed. When completed, findings are included and can be filtered "
        "by category, type, and severity, with pagination support."
    ),
)
async def get_check(
    check_id: str,
    db: AsyncSession = Depends(get_db),
    redis: Optional[Redis] = Depends(get_redis),
    category: Optional[FindingCategory] = Query(default=None),
    finding_type: Optional[FindingType] = Query(default=None),
    severity: Optional[LinkAnalysisSeverity] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=200, ge=1, le=200),
) -> LinkAnalysisCheckResponse:
    """Unified GET handler — returns status/progress or completed results."""
    check = await _get_check_or_404(check_id, db)
    redis_repo = LinkAnalysisRepository(db, redis=redis)

    status_str = _str_status(check.status)

    # --- Redis-first for live progress ---
    if redis is not None and status_str in (
        LinkAnalysisCheckStatus.QUEUED.value,
        LinkAnalysisCheckStatus.PROCESSING.value,
    ):
        redis_status = await redis_repo.get_status(check.id)
        if redis_status:
            redis_status.update({
                "check_id": check.id,
                "url": check.url,
                "domain": check.domain,
            })

    # --- Failed ---
    if status_str == LinkAnalysisCheckStatus.FAILED.value:
        return LinkAnalysisCheckResponse(
            check_id=check.id,
            url=check.url,
            domain=check.domain,
            status=check.status,
            task_id=check.task_id,
            progress=check.progress,
            error=check.error,
            checked_at=check.updated_at.isoformat() if check.updated_at else None,
        )

    # --- Completed — fetch paginated findings from DB ---
    if status_str == LinkAnalysisCheckStatus.COMPLETED.value:
        offset = (page - 1) * page_size
        findings = await redis_repo.get_findings(
            check_id=check.id,
            category=category,
            finding_type=finding_type,
            severity=severity,
            limit=page_size,
            offset=offset,
        )
        total = await redis_repo.total_finding_count(check.id)

        summary_data = check.summary or {}
        from .schema import LinkAnalysisSummary
        summary = LinkAnalysisSummary(**{
            k: v for k, v in summary_data.items()
            if k in LinkAnalysisSummary.model_json_schema()["properties"]
        })

        finding_responses = [
            FindingResponse(
                category=f.category,
                type=f.type,
                severity=f.severity,
                target_url=f.target_url,
                status_code=f.status_code,
                final_url=f.final_url,
                evidence=f.evidence,
                recommendation=f.recommendation,
            )
            for f in findings
        ]

        return LinkAnalysisCheckResponse(
            check_id=check.id,
            url=check.url,
            domain=check.domain,
            status=check.status,
            task_id=check.task_id,
            checked_at=check.updated_at.isoformat() if check.updated_at else None,
            overall_status=_str_status(check.overall_status),
            severity=_str_status(check.severity),
            cost_seconds=check.cost_seconds,
            summary=summary,
            findings=finding_responses,
            total_findings=total,
        )

    # --- Queued / Processing ---
    return LinkAnalysisCheckResponse(
        check_id=check.id,
        url=check.url,
        domain=check.domain,
        status=check.status,
        task_id=check.task_id,
        progress=check.progress,
        error=check.error,
    )
