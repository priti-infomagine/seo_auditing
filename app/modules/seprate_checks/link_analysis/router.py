"""Asynchronous Link Analysis API routes with polling.

Endpoints:
- POST /check               — Queue an asynchronous link analysis (HTTP 202)
- GET  /check/{check_id}    — Poll progress and retrieve status or results

The GET endpoint returns a unified response: when queued/processing it
returns status + progress; when completed it includes findings, summary,
and overall verdict. Use query filters (category, type, severity) to
narrow the findings list and pagination to browse.
"""
import asyncio
from typing import Optional ,List
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
        body.validate_url()
        check = await LinkAnalysisService.prepare_check(body.url, db, redis=redis, max_pages=body.max_pages)

        # Offload synchronous Celery send_task to avoid blocking the event loop
        task = await asyncio.to_thread(
            celery_app.send_task,
            "link_analysis.run_check",
            args=[str(check.id), check.url],
            kwargs={"max_pages": body.max_pages},
            queue="crawler",
        )
        check.task_id = task.id
        await db.commit()

        return LinkAnalysisQueuedResponse(
            check_id=check.id,
            task_id=task.id,
            url=check.url,
            domain=check.domain,
            status=check.status if isinstance(check.status, LinkAnalysisCheckStatus) else LinkAnalysisCheckStatus(check.status),
            max_pages=body.max_pages,
            created_at=check.created_at.isoformat() if check.created_at else None,
        )
    except ValueError as exc:
        logger.warning("check_links: validation error: %s", exc)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except HTTPException:
        raise
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
        "or failed. When completed, findings and pages are included and can be filtered "
        "by category, type, severity, search keywords, or page properties with pagination support."
    ),
)
async def get_check(
    check_id: str,
    db: AsyncSession = Depends(get_db),
    redis: Optional[Redis] = Depends(get_redis),
    category: Optional[str] = Query(default=None, description="Filter findings by category (e.g. 'standard', 'optimization')"),
    type: Optional[str] = Query(default=None, alias="type", description="Filter findings by type (e.g. 'broken_internal', 'orphan')"),
    finding_type: Optional[str] = Query(default=None, description="Alias for type filter"),
    severity: Optional[str] = Query(default=None, description="Filter findings by severity (e.g. 'high', 'medium', 'low')"),
    search: Optional[str] = Query(default=None, description="Search term to match target URL in findings"),
    page_url: Optional[str] = Query(default=None, description="Filter page-by-page results by exact or partial URL"),
    is_orphan: Optional[bool] = Query(default=None, description="Filter pages: only orphan pages (true) or non-orphan (false)"),
    is_dead_end: Optional[bool] = Query(default=None, description="Filter pages: only dead-end pages (true)"),
    has_issues: Optional[bool] = Query(default=None, description="Filter pages: only pages with detected issues (true)"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=200, ge=1, le=500),
) -> LinkAnalysisCheckResponse:
    """Unified GET handler — returns status/progress or completed results."""
    check = await _get_check_or_404(check_id, db)
    redis_repo = LinkAnalysisRepository(db, redis=redis)

    status_str = _str_status(check.status)
    live_progress = check.progress

    # --- Redis-first for live progress ---
    if redis is not None and status_str in (
        LinkAnalysisCheckStatus.QUEUED.value,
        LinkAnalysisCheckStatus.PROCESSING.value,
    ):
        try:
            redis_status = await redis_repo.get_status(check.id)
            if redis_status and "progress" in redis_status:
                live_progress = redis_status["progress"]
        except Exception as exc:
            logger.warning("get_check: failed to read Redis progress for %s: %s", check.id, exc)

    # --- Failed ---
    if status_str == LinkAnalysisCheckStatus.FAILED.value:
        return LinkAnalysisCheckResponse(
            check_id=check.id,
            url=check.url,
            domain=check.domain,
            status=LinkAnalysisCheckStatus.FAILED,
            task_id=check.task_id,
            progress=check.progress,
            error=check.error,
            checked_at=check.updated_at.isoformat() if check.updated_at else None,
        )

    # --- Completed — fetch paginated findings from DB ---
    if status_str == LinkAnalysisCheckStatus.COMPLETED.value:
        resolved_type = type or finding_type
        offset = (page - 1) * page_size
        findings = await redis_repo.get_findings(
            check_id=check.id,
            category=category,
            finding_type=resolved_type,
            severity=severity,
            search=search,
            limit=page_size,
            offset=offset,
        )
        total = await redis_repo.count_findings(
            check_id=check.id,
            category=category,
            finding_type=resolved_type,
            severity=severity,
            search=search,
        )

        summary_data = check.summary or {}
        from .schema import LinkAnalysisSummary, PageAnalysisItem, SourceReference
        allowed_keys = getattr(LinkAnalysisSummary, "model_fields", None) or LinkAnalysisSummary.model_json_schema()["properties"]
        summary = LinkAnalysisSummary(**{
            k: v for k, v in summary_data.items()
            if k in allowed_keys
        })

        stored_pages = await redis_repo.get_pages(check.id)
        if stored_pages:
            raw_pages = [
                {
                    "url": page.page_url,
                    "status_code": page.status_code,
                    "depth": page.depth,
                    "inbound_internal_links": page.inbound_internal_links,
                    "outbound_internal_links": page.outbound_internal_links,
                    "outbound_external_links": page.outbound_external_links,
                    "total_links": page.outbound_internal_links + page.outbound_external_links,
                    "unique_links": len({
                        link.get("target_url")
                        for link in page.internal_links + page.external_links
                        if link.get("target_url")
                    }),
                    "unique_internal_targets": len({
                        link.get("target_url")
                        for link in page.internal_links
                        if link.get("target_url")
                    }),
                    "unique_external_targets": len({
                        link.get("target_url")
                        for link in page.external_links
                        if link.get("target_url")
                    }),
                    "broken_internal_links": page.broken_internal_links,
                    "broken_external_links": page.broken_external_links,
                    "internal_links": page.internal_links,
                    "external_links": page.external_links,
                    "is_orphan": page.is_orphan,
                    "is_dead_end": page.is_dead_end,
                    "issues": page.issues,
                }
                for page in stored_pages
            ]
        else:
            raw_pages = summary_data.get("pages", [])
        page_items: List[PageAnalysisItem] = []
        for p in raw_pages:
            p_dict = p if isinstance(p, dict) else (p.model_dump() if hasattr(p, "model_dump") else p.__dict__)
            if page_url and page_url.lower() not in str(p_dict.get("url", "")).lower():
                continue
            if is_orphan is not None and bool(p_dict.get("is_orphan")) != is_orphan:
                continue
            if is_dead_end is not None and bool(p_dict.get("is_dead_end")) != is_dead_end:
                continue
            if has_issues is True and not p_dict.get("issues"):
                continue
            if has_issues is False and p_dict.get("issues"):
                continue
            internal_links = p_dict.get("internal_links", [])
            external_links = p_dict.get("external_links", [])
            p_dict.setdefault(
                "total_links",
                p_dict.get("outbound_internal_links", 0)
                + p_dict.get("outbound_external_links", 0),
            )
            p_dict.setdefault("unique_links", len({
                link.get("target_url")
                for link in internal_links + external_links
                if isinstance(link, dict) and link.get("target_url")
            }))
            p_dict.setdefault("unique_internal_targets", len({
                link.get("target_url")
                for link in internal_links
                if isinstance(link, dict) and link.get("target_url")
            }))
            p_dict.setdefault("unique_external_targets", len({
                link.get("target_url")
                for link in external_links
                if isinstance(link, dict) and link.get("target_url")
            }))
            page_items.append(PageAnalysisItem(**p_dict))

        finding_responses = []
        for f in findings:
            evidence = f.evidence or {}
            raw_sources = evidence.get("sources", [])
            total_sources = evidence.get("total_sources", len(raw_sources))
            sources_list = [
                SourceReference(
                    source_url=s.get("source_url", ""),
                    anchor_text=s.get("anchor_text", ""),
                    rel=s.get("rel", []),
                )
                if isinstance(s, dict) else s
                for s in raw_sources
            ]

            # Simplify recommendation to a clean, useful action string or keep structured dict
            rec_text = None
            if isinstance(f.recommendation, dict):
                rec_text = f.recommendation.get("action") or f.recommendation.get("title")
            elif isinstance(f.recommendation, str):
                rec_text = f.recommendation

            finding_responses.append(
                FindingResponse(
                    category=f.category,
                    type=f.type,
                    severity=f.severity,
                    target_url=f.target_url,
                    status_code=f.status_code,
                    final_url=f.final_url,
                    total_sources=total_sources,
                    sources=sources_list,
                    recommendation=rec_text or f.recommendation,
                    evidence=f.evidence,
                )
            )

        return LinkAnalysisCheckResponse(
            check_id=check.id,
            url=check.url,
            domain=check.domain,
            status=LinkAnalysisCheckStatus.COMPLETED,
            task_id=check.task_id,
            checked_at=check.updated_at.isoformat() if check.updated_at else None,
            overall_status=_str_status(check.overall_status),
            severity=_str_status(check.severity),
            cost_seconds=check.cost_seconds,
            summary=summary,
            pages=page_items,
            findings=finding_responses,
            total_findings=total,
        )

    # --- Queued / Processing ---
    return LinkAnalysisCheckResponse(
        check_id=check.id,
        url=check.url,
        domain=check.domain,
        status=LinkAnalysisCheckStatus(status_str) if status_str in [s.value for s in LinkAnalysisCheckStatus] else LinkAnalysisCheckStatus.QUEUED,
        task_id=check.task_id,
        progress=live_progress,
        error=check.error,
    )
