"""
Lighthouse check API routes.

POST /lighthouse/check              — Queue a full Lighthouse check (async)
GET  /lighthouse/status/{check_id}  — Poll progress (crawl + pagespeed phases)
GET  /lighthouse/task/{task_id}     — Poll Celery task state (optional)
GET  /lighthouse/results/{check_id} — Retrieve stored page results by check_id

Design notes
------------
* The check is asynchronous: the POST creates a tracking ``CrawlJob`` (whose
  ``id`` is the ``check_id``, mirroring the audit module where
  ``CrawlJob.id == audit_id``) and enqueued a Celery task on the ``lighthouse``
  queue, then returns 202 immediately.
* Progress is DB-persisted (``CrawlJob.crawl_config['phase']`` + count of
  ``lighthouse_page_results``) so /status works even if the worker dies.
* The CrawlJob.status lifecycle is owned here through the pagespeed phase:
  queued → crawling (crawl) → crawling (pagespeed) → completed/failed.
"""
import asyncio
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.#loggger import #loggger
from app.shared.tasks.celery_app import celery_app
from app.modules.crawler.models.crawl_jobs import CrawlJob
from app.modules.crawler.repositories.crawl_job_repository import CrawlJobRepository
from app.modules.seprate_checks.google_lighthouse_check.repository import (
    LighthousePageResultRepository,
)
from app.modules.seprate_checks.google_lighthouse_check.schema import (
    LighthouseCheckQueuedResponse,
    LighthouseCheckResponse,
    LighthouseCheckRequest,
    LighthouseCheckStatusResponse,
)
from app.modules.seprate_checks.google_lighthouse_check.services import (
    LighthouseCheckService,
)

router = APIRouter()


@router.post(
    "/check",
    response_model=LighthouseCheckQueuedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Queue a Google Lighthouse/Pagespeed check",
    description=(
        "Creates a tracking CrawlJob (`check_id == CrawlJob.id`) and enqueues a "
        "Celery task on the `lighthouse` queue. The task crawls the seed URL, "
        "discovers internal pages, then runs the PageSpeed Insights (Lighthouse) "
        "API concurrently per page. Returns immediately with `check_id`, "
        "`task_id`, and `domain`. Poll `GET /lighthouse/status/{check_id}` for "
        "progress and `GET /lighthouse/results/{check_id}` for results."
    ),
)
async def run_lighthouse_check(
    body: LighthouseCheckRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    1. Validate input (device/category/max_pages/url).
    2. Create a tracking CrawlJob (`check_id = job.id`, status="queued").
    3. Enqueue `lighthouse.run_check` on the `lighthouse` queue.
    4. Persist the Celery `task_id` back onto the job for correlation.
    5. Return 202 with check_id, task_id, domain, and poll/result URLs.
    """
    #loggger.info(
        f"POST /lighthouse/check — url={body.url}, device={body.device}, "
        f"max_pages={body.max_pages}, category={body.effective_category}"
    )

    service = LighthouseCheckService()

    # Phase: prepare (validate + create tracking CrawlJob).
    try:
        setup = await service.prepare_check(
            db=db,
            url=body.url,
            device=body.device,
            max_pages=body.max_pages,
            category=body.effective_category,
            pagespeed_concurrency=service.PAGESPEED_CONCURRENCY,
        )
    except HTTPException:
        raise
    except ValueError as e:
        loggger.warning(f"Lighthouse check rejected — validation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        loggger.error(f"Unexpected error preparing lighthouse check: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while preparing the lighthouse check",
        )

    check_id = setup["check_id"]

    # Phase: enqueue the Celery task.  send_task is a synchronous (blocking)
    # Redis operation — run it in a thread to avoid stalling the event loop,
    # mirroring POST /audit/analyze.
    try:
        async_result = await asyncio.to_thread(
            celery_app.send_task,
            "lighthouse.run_check",
            args=[
                check_id,
                setup["url"],
                setup["device"],
                setup["max_pages"],
            ],
            kwargs={
                "category": setup["categories"],
                "pagespeed_concurrency": setup["pagespeed_concurrency"],
            },
            queue="lighthouse",
        )
    except Exception as e:
        loggger.error(f"Failed to enqueue lighthouse check task: {e}", exc_info=True)
        await service.mark_check_failed(UUID(check_id), f"enqueue_failed: {e}"[:1024])
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to enqueue lighthouse check task, please retry",
        )

    # Phase: record the task id for correlation.
    await service.record_task_id(db, check_id, async_result.id)

    #loggger.info(
        f"Lighthouse check queued: check_id={check_id}, "
        f"task_id={async_result.id}, domain={setup['domain']}"
    )

    return LighthouseCheckQueuedResponse(
        success=True,
        status="queued",
        message="Lighthouse check queued successfully — poll the status URL for progress",
        check_id=UUID(check_id),
        task_id=async_result.id,
        url=setup["url"],
        domain=setup["domain"],
        device=setup["device"],
        categories=setup["categories"],
        status_url=f"/api/v1/lighthouse/status/{check_id}",
        result_url=f"/api/v1/lighthouse/results/{check_id}",
    )


@router.get(
    "/status/{check_id}",
    response_model=LighthouseCheckStatusResponse,
    summary="Poll lighthouse check progress",
    description=(
        "Returns the live progress of a check: crawl-phase page counts and "
        "pagespeed-phase result counts (succeeded/failed), derived from the "
        "tracking CrawlJob row + lighthouse_page_results table. Survives worker "
        "death since all state is persisted to the database."
    ),
)
async def get_lighthouse_status(
    check_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get the status + progress of a lighthouse check by check_id."""
    loggger.info(f"GET /lighthouse/status/{check_id}")

    try:
        check_uuid = UUID(check_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid check_id format: {check_id}",
        )

    try:
        job_repo = CrawlJobRepository(db)
        job: CrawlJob | None = await job_repo.get_by_id(check_uuid)
        if job is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Lighthouse check {check_id} not found",
            )

        cfg = job.crawl_config or {}
        phase = cfg.get("phase", "queued")
        task_id = cfg.get("task_id")
        pagespeed_total = int(cfg.get("pagespeed_total") or 0)

        counts = await LighthousePageResultRepository(db).get_count_by_check_id(check_uuid)
        pagespeed_succeeded = counts["success"]
        pagespeed_failed = counts["failed"]
        pagespeed_checked = pagespeed_succeeded + pagespeed_failed

        # pagespeed_total is the crawl output; if not yet recorded, fall back
        # to the crawl-discovered count (may be 0 mid-crawl).
        if pagespeed_total == 0:
            pagespeed_total = job.pages_crawled or job.pages_discovered or 0

        # Overall progress percent, phase-aware.
        progress_percent: int | None
        if phase in ("completed", "failed"):
            progress_percent = 100
        elif phase == "queued":
            progress_percent = 0
        elif phase == "crawl":
            # Use the orchestrator's progress, or fall back to discover/crawl ratio.
            progress_percent = (
                job.progress_percent
                or (
                    int((job.pages_crawled / job.pages_discovered) * 100)
                    if job.pages_discovered
                    else 0
                )
            )
        else:  # pagespeed
            progress_percent = (
                int((pagespeed_checked / pagespeed_total) * 100)
                if pagespeed_total
                else 0
            )

        return LighthouseCheckStatusResponse(
            check_id=job.id,
            task_id=task_id,
            status=job.status,
            phase=phase,
            domain=job.domain,
            device=(job.crawl_config or {}).get("device", "mobile"),
            categories=(job.crawl_config or {}).get(
                "categories", ["performance", "seo", "best-practices", "accessibility"],
            ),
            pages_discovered=job.pages_discovered or 0,
            pages_crawled=job.pages_crawled or 0,
            pagespeed_total=pagespeed_total,
            pagespeed_checked=pagespeed_checked,
            pagespeed_succeeded=pagespeed_succeeded,
            pagespeed_failed=pagespeed_failed,
            progress_percent=progress_percent,
            started_at=(
                job.started_at.isoformat() if job.started_at else None
            ),
            completed_at=(
                job.completed_at.isoformat() if job.completed_at else None
            ),
            duration_ms=job.duration_ms,
            error=job.error,
            result_url=f"/api/v1/lighthouse/results/{check_id}",
        )
    except HTTPException:
        raise
    except Exception as e:
        #loggger.error(
            f"GET /lighthouse/status/{check_id}: unexpected error - {e}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while fetching lighthouse status",
        )


@router.get(
    "/task/{task_id}",
    summary="Poll lighthouse task state (Celery)",
    description=(
        "Read-only status check against the Celery result backend for the task "
        "enqueued by POST /lighthouse/check. Prefer GET /status/{check_id} "
        "for durable, DB-persisted progress; this is provided for parity with "
        "GET /audit/analyze/task/{task_id}."
    ),
)
async def get_lighthouse_task_status(task_id: str) -> dict:
    """Poll the Celery task state for a lighthouse check."""
    loggger.info(f"GET /lighthouse/task/{task_id}")
    async_result = celery_app.AsyncResult(task_id)
    response: dict = {"task_id": task_id, "state": async_result.state}
    if async_result.state == "PROGRESS":
        response["meta"] = async_result.info
    elif async_result.state == "SUCCESS":
        response["result"] = async_result.result
    elif async_result.state == "FAILURE":
        response["error"] = str(async_result.result)
    return response


@router.get(
    "/results/{check_id}",
    response_model=list[LighthouseCheckResponse],
    summary="Get Lighthouse check results",
    description=(
        "Retrieve all lighthouse page results for a given check_id. Results are "
        "written progressively as each PageSpeed API call completes, so polling "
        "this endpoint during the check returns rows-so-far."
    ),
)
async def get_lighthouse_results(
    check_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get all LighthousePageResult rows for a check_id."""
    try:
        check_uuid = UUID(check_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid check_id format",
        )

    try:
        # Distinguish "no such check" (404) from "check exists but not done" (200, []).
        job = await CrawlJobRepository(db).get_by_id(check_uuid)
        if job is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Lighthouse check {check_id} not found",
            )

        rows = await LighthousePageResultRepository(db).get_by_check_id(check_uuid)

        return [
            LighthouseCheckResponse(
                id=r.id,
                url=r.url,
                device=r.device.value if hasattr(r.device, "value") else r.device,
                status=r.status.value if hasattr(r.status, "value") else r.status,
                reason=r.reason,
                performance_score=r.performance_score,
                seo_score=r.seo_score,
                fcp_ms=r.fcp_ms,
                lcp_ms=r.lcp_ms,
                tbt_ms=r.tbt_ms,
                cls=r.cls,
            )
            for r in rows
        ]
    except HTTPException:
        raise
    except Exception as e:
        loggger.error(f"Lighthouse results fetch failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )
