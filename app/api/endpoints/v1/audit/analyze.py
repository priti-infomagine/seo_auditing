"""
POST /audit/analyze — Complete crawl → parse → score SEO audit pipeline.

Takes a URL as input, performs the full pipeline:
1. Crawls multiple pages (sitemap-first, BFS-fallback)
2. Persists crawl data to DB (CrawlPage, snapshot, SEO data, network data)
3. DB-backed parse → rule evaluation → scoring
4. Returns per-page breakdown with scores, rule results, and links analysis
"""
import asyncio

import uuid
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.logger import logger
from app.core.config import settings
from app.modules.audit.schemas.audit_schemas import (
    AuditAnalyzeRequest,
    AuditAnalyzeQueuedResponse,
)
from app.modules.crawler.models.crawl_jobs import CrawlJob
from app.modules.crawler.repositories.crawl_job_repository import CrawlJobRepository
from app.shared.tasks.celery_app import celery_app
from app.shared.utils.url_utils import get_domain

router = APIRouter()


@router.post(
    "/analyze",
    response_model=AuditAnalyzeQueuedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Queue a complete SEO audit pipeline",
    description=(
        "Creates a crawl job and enqueues it on the crawler queue. The crawl "
        "then triggers the parse → evaluate → score analysis pipeline. Returns "
        "immediately with crawl_id / audit_id / task_id and status URLs for "
        "polling. The final result is fetched via GET /audit/result/{audit_id}."
    ),
)
async def analyze_website(
    body: AuditAnalyzeRequest,
    format: Literal["full", "compact"] = Query(
        "full",
        description=(
            "Desired shape of the audit response. 'full' (default) = legacy "
            "UnifiedAuditResponse with per-page evidence. 'compact' = new "
            "AuditOverview (5–20 KB)."
        ),
    ),
    db: AsyncSession = Depends(get_db),
) -> AuditAnalyzeQueuedResponse:
    """
    Queue a complete crawl → parse → score SEO audit pipeline.

    The request is validated, a CrawlJob is persisted, and the
    `crawler.crawl_website` Celery task is enqueued (queue="crawler"). When the
    crawl completes it fires `audit.run_analysis_pipeline` (queue="audit") which
    runs parse → evaluate → score. This endpoint returns immediately.

    Args:
        body: AuditAnalyzeRequest containing URL and crawl limits
        db: Database session

    Returns:
        AuditAnalyzeQueuedResponse with audit_id, crawl_id, task_id and URLs.

    Raises:
        HTTPException: If the URL is invalid or the job cannot be queued.
    """
    logger.info(
        f"POST /audit/analyze - Queuing audit for URL: {body.url}, "
        f" max_pages: {body.max_pages}, "
    )

    anonymous_user_id = uuid.uuid4()

    try:
        url_str = str(body.url)
        domain = get_domain(url_str)
        if not domain:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid URL: {body.url} - could not extract domain",
            )

        audit_id = uuid.uuid4()

        effective_max_pages = (
             settings.CRAWL_MAX_PAGES
            if body.max_pages is not None
            else settings.CRAWL_MAX_PAGES
        )
        effective_max_depth = body.max_depth if body.max_depth is not None else 5

        crawl_config = {
            "max_depth": effective_max_depth,
            "max_pages": effective_max_pages,
            "concurrency": body.concurrency,
            "request_timeout": 120,
            "delay_ms": 0,
            "follow_redirects": True,
            "respect_robots": True,
            "auto_analyze": body.full_pipeline,
        }
        crawl_job = CrawlJob(
            id=audit_id,
            user_id=anonymous_user_id,
            url=url_str,
            domain=domain,
            status="queued",
            max_pages=effective_max_pages,
            max_depth=effective_max_depth,
            crawl_config=crawl_config,
        )
        job_repo = CrawlJobRepository(db)
        await job_repo.create(crawl_job)

        logger.info(
            f"CrawlJob created: audit_id={audit_id}, domain={domain}"
        )

        async_result = await asyncio.to_thread(
            celery_app.send_task,
            "crawler.crawl_website",
            args=[str(audit_id), url_str, str(anonymous_user_id)],
            kwargs={"force": body.force},
            queue="crawler",
        )

        logger.info(
            f"Audit enqueued: audit_id={audit_id}, task_id={async_result.id}, queued on 'crawler'"
        )

        fmt = "" if format == "full" else f"?format={format}"

        return AuditAnalyzeQueuedResponse(
            success=True,
            status="queued",
            message="Audit queued successfully — poll the task URL for progress",
            url=url_str,
            domain=domain,
            audit_id=str(audit_id),
            task_id=async_result.id,
            task_status_url=f"/api/v1/audit/analyze/task/{async_result.id}",
            crawl_status_url=f"/api/v1/crawler/status/{audit_id}",
            pipeline_status_url=f"/api/v1/audit/status/{audit_id}",
            result_url=f"/api/v1/audit/result/{audit_id}{fmt}",
            full_pipeline=body.full_pipeline,
            result_project_url=f"/api/v1/audit/result/{audit_id}{fmt}",
        )

    except ValueError as e:
        logger.warning(f"Invalid URL provided: {body.url} - {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid URL: {str(e)}"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Unexpected error queuing audit for URL: {body.url}", exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while queuing the audit"
        )


@router.get(
    "/analyze/task/{task_id}",
    summary="Poll audit crawl task state",
    description=(
        "Read-only status check against the Celery result backend for the "
        "crawl task enqueued by POST /audit/analyze."
    ),
)
async def get_analyze_task_status(
    task_id: str,
) -> dict:
    logger.info(f"GET /audit/analyze/task/{task_id}")
    async_result = celery_app.AsyncResult(task_id)
    response: dict = {
        "task_id": task_id,
        "state": async_result.state,
    }
    if async_result.state == "PROGRESS":
        response["meta"] = async_result.info
    elif async_result.state == "SUCCESS":
        response["result"] = async_result.result
    elif async_result.state == "FAILURE":
        response["error"] = str(async_result.result)
    return response


@router.get("/health", tags=["Audit"])
async def audit_health_check():
    """Health check for audit endpoint."""
    try:
        return {
            "status": "healthy",
            "service": "audit-analyze",
            "endpoints": ["/api/v1/audit/analyze"],
        }
    except Exception as exc:
        logger.error(f"audit_health_check: unexpected error: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Audit service health check failed",
        )
