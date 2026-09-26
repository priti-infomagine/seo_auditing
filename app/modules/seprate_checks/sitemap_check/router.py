"""Asynchronous Sitemap Check API routes with polling.

Endpoints:
- POST /check               — Queue an asynchronous sitemap check (HTTP 202)
- GET  /status/{check_id}   — Poll progress and retrieve results upon completion
- GET  /result/{check_id}   — Retrieve stored results once completed
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.logger import logger
from app.shared.tasks.celery_app import celery_app

from .model import SitemapCheck, SitemapCheckStatus
from .repository import SitemapCheckRepository
from .schema import (
    SitemapCheckQueuedResponse,
    SitemapCheckRequest,
    SitemapCheckResultResponse,
    SitemapCheckStatusResponse,
    SitemapFileItem,
    SitemapIssue,
    SitemapRecommendation,
    SitemapSummary,
)
from .service import SitemapCheckService

router = APIRouter()


def _str_status(val) -> str:
    if hasattr(val, "value"):
        return str(val.value)
    return str(val) if val is not None else ""


def _to_result_response(check: SitemapCheck) -> SitemapCheckResultResponse:
    """Serialize a completed SitemapCheck DB model to SitemapCheckResultResponse."""
    summary_data = check.summary or {}
    summary = SitemapSummary(
        total_sitemaps=summary_data.get("total_sitemaps", 0),
        sitemap_indexes=summary_data.get("sitemap_indexes", 0),
        url_sitemaps=summary_data.get("url_sitemaps", 0),
        total_urls_declared=summary_data.get("total_urls_declared", 0),
        total_issues=summary_data.get("total_issues", 0),
    )

    sitemap_items = [
        SitemapFileItem(
            url=s.get("url", ""),
            is_index=s.get("is_index", False),
            status_code=s.get("status_code", 0),
            content_type=s.get("content_type", ""),
            entry_count=s.get("entry_count", 0),
            content_length=s.get("content_length", 0),
            response_time_ms=s.get("response_time_ms", 0),
            error=s.get("error"),
            issues=[
                SitemapIssue(
                    code=i.get("code", "unknown"),
                    severity=i.get("severity", "medium"),
                    status=i.get("status", "warning"),
                    message=i.get("message", ""),
                    evidence=i.get("evidence"),
                )
                for i in s.get("issues", [])
            ],
            recommendations=[
                SitemapRecommendation(
                    code=r.get("code", "unknown"),
                    priority=r.get("priority", "medium"),
                    title=r.get("title", ""),
                    message=r.get("message", ""),
                    fix=r.get("fix", ""),
                    where_to_fix=r.get("where_to_fix", "sitemap_xml"),
                    evidence=r.get("evidence"),
                )
                for r in s.get("recommendations", [])
            ],
        )
        for s in (check.sitemaps or [])
    ]

    findings = [
        SitemapIssue(
            code=f.get("code", "unknown"),
            severity=f.get("severity", "medium"),
            status=f.get("status", "warning"),
            message=f.get("message", ""),
            evidence=f.get("evidence"),
        )
        for f in (check.findings or [])
    ]

    recommendations = [
        SitemapRecommendation(
            code=r.get("code", "unknown"),
            priority=r.get("priority", "medium"),
            title=r.get("title", ""),
            message=r.get("message", ""),
            fix=r.get("fix", ""),
            where_to_fix=r.get("where_to_fix", "sitemap_xml"),
            evidence=r.get("evidence"),
        )
        for r in (check.recommendations or [])
    ]

    return SitemapCheckResultResponse(
        check_id=check.id,
        url=check.url,
        domain=check.domain,
        status=check.status,
        checked_at=check.updated_at.isoformat() if check.updated_at else None,
        overall_status=_str_status(check.overall_status) if check.overall_status else None,
        severity=_str_status(check.severity) if check.severity else None,
        summary=summary,
        sitemaps=sitemap_items,
        findings=findings,
        recommendations=recommendations,
        cost_seconds=check.cost_seconds,
    )


async def _get_check_or_404(check_id: str, db: AsyncSession) -> SitemapCheck:
    try:
        parsed_id = UUID(check_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid check ID format (must be a valid UUID)",
        ) from exc

    check = await SitemapCheckRepository(db).get(parsed_id)
    if check is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sitemap check with ID '{check_id}' not found",
        )
    return check


@router.post(
    "/check",
    response_model=SitemapCheckQueuedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Queue an asynchronous Sitemap audit",
    description=(
        "Enqueues an asynchronous sitemap check on the `crawler` queue. "
        "Returns immediately with HTTP 202 containing the `check_id`. "
        "Poll `GET /api/v1/sitemap/status/{check_id}` for progress and results."
    ),
)
async def check_sitemap(
    body: SitemapCheckRequest,
    db: AsyncSession = Depends(get_db),
) -> SitemapCheckQueuedResponse:
    try:
        check = await SitemapCheckService.prepare_check(body.url, db)

        # Dispatch background task to Celery crawler queue
        task = celery_app.send_task(
            "sitemap.run_check",
            args=[str(check.id), check.url],
            queue="crawler",
        )
        check.task_id = task.id
        await db.commit()

        return SitemapCheckQueuedResponse(
            check_id=check.id,
            task_id=task.id,
            url=check.url,
            domain=check.domain,
            status=check.status,
            created_at=check.created_at.isoformat() if check.created_at else None,
        )
    except ValueError as exc:
        logger.warning("check_sitemap: validation error: %s", exc)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        logger.error("check_sitemap: unexpected error: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while queuing the sitemap check",
        )


@router.get(
    "/status/{check_id}",
    response_model=SitemapCheckStatusResponse,
    summary="Poll status and progress of a sitemap check",
    description=(
        "Poll this endpoint to check if the job is queued, processing, completed, "
        "or failed. When completed, the full results payload is returned in `data`."
    ),
)
async def get_check_status(
    check_id: str,
    db: AsyncSession = Depends(get_db),
) -> SitemapCheckStatusResponse:
    check = await _get_check_or_404(check_id, db)

    status_str = _str_status(check.status)
    return SitemapCheckStatusResponse(
        check_id=check.id,
        url=check.url,
        domain=check.domain,
        status=check.status,
        progress=check.progress,
        error=check.error,
    )


@router.get(
    "/result/{check_id}",
    response_model=SitemapCheckResultResponse,
    summary="Get completed sitemap check results",
    description="Retrieve the complete audit findings, sitemaps, and recommendations once completed.",
)
async def get_check_result(
    check_id: str,
    db: AsyncSession = Depends(get_db),
) -> SitemapCheckResultResponse:
    check = await _get_check_or_404(check_id, db)

    status_str = _str_status(check.status)
    if status_str != SitemapCheckStatus.COMPLETED.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Sitemap check is not completed yet (current status: '{status_str}')",
        )

    return _to_result_response(check)
