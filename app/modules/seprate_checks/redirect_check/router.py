"""API routes for domain-level redirect checking with SSE streaming.

Endpoints:
- POST /check              — Queue a domain redirect check (HTTP 202)
- GET  /status/{check_id}  — Poll progress and retrieve results
- GET  /stream/{check_id}  — SSE stream of per-URL redirect results
- GET  /result/{check_id}  — Retrieve final completed results
"""
from __future__ import annotations

import asyncio
import json
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.logger import logger
from app.core.redis import get_redis
from app.modules.seprate_checks.redirect_check.schema import (
    RedirectCheckQueuedResponse,
    RedirectCheckRequest,
    RedirectCheckResultResponse,
    RedirectCheckStatusResponse,
    RedirectFinding,
    RedirectSummary,
    RedirectUrlResult,
)
from app.modules.seprate_checks.redirect_check.service import RedirectCheckService
from app.modules.seprate_checks.redirect_check.sse import sse_event_stream
from app.modules.streaming_audit.models.streaming_audit_run import StreamingAuditStatus
from app.modules.streaming_audit.services.streaming_audit_service import (
    StreamingAuditService,
)
from app.shared.tasks.celery_app import celery_app

router = APIRouter()


def _str_status(val: Any) -> str:
    if hasattr(val, "value"):
        return str(val.value)
    return str(val) if val is not None else ""


async def _get_run_or_404(
    check_id: str,
    db: AsyncSession,
) -> Any:
    try:
        parsed_id = UUID(check_id)
    except (ValueError, AttributeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid check ID format (must be a valid UUID)",
        ) from exc

    repo = StreamingAuditService(db)
    run = await repo.get_run(parsed_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Redirect check with ID '{check_id}' not found",
        )
    return run


@router.post(
    "/check",
    response_model=RedirectCheckQueuedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Queue a domain-level redirect check",
    description=(
        "Discovers all internal URLs from sitemap.xml and crawling the domain, "
        "then checks each URL for redirect chains. Results stream via SSE. "
        "Returns immediately with an HTTP 202 containing the `check_id`."
    ),
)
async def check_redirects(
    body: RedirectCheckRequest,
    db: AsyncSession = Depends(get_db),
    redis: Redis | None = Depends(get_redis),
) -> RedirectCheckQueuedResponse:
    try:
        service = RedirectCheckService(redis=redis)
        audit_id = await service.prepare_check(
            body.domain, db, max_urls=body.max_urls
        )

        task = await asyncio.to_thread(
            celery_app.send_task,
            "redirect_check.run_domain_check",
            args=[audit_id, body.domain, body.max_urls],
            queue="crawler",
        )

        return RedirectCheckQueuedResponse(
            check_id=UUID(audit_id),
            task_id=task.id,
            domain=body.domain,
            status="queued",
            max_urls=body.max_urls,
            created_at=None,
            status_url=f"/api/v1/redirect-check/status/{audit_id}",
            stream_url=f"/api/v1/redirect-check/stream/{audit_id}",
        )
    except ValueError as exc:
        logger.warning("check_redirects: validation error: %s", exc)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        logger.error("check_redirects: unexpected error: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while queuing the redirect check",
        )


@router.get(
    "/status/{check_id}",
    response_model=RedirectCheckStatusResponse,
    summary="Poll status and progress of a redirect check",
)
async def get_redirect_check_status(
    check_id: str,
    db: AsyncSession = Depends(get_db),
    redis: Redis | None = Depends(get_redis),
) -> RedirectCheckStatusResponse:
    run = await _get_run_or_404(check_id, db)

    live_progress: dict[str, Any] = {}
    if run.final_summary:
        live_progress = run.final_summary.get("summary", {})

    return RedirectCheckStatusResponse(
        check_id=check_id,
        domain=run.domain,
        status=run.status,
        progress=live_progress,
        discovered_count=run.discovered_count,
        queued_count=run.queued_count,
        processing_count=run.processing_count,
        completed_count=run.completed_count,
        failed_count=run.failed_count,
        error=run.error_info,
    )


@router.get(
    "/stream/{check_id}",
    summary="SSE stream of redirect check results",
    description=(
        "Establishes a Server-Sent Events connection that streams per-URL "
        "redirect results in real time as they are checked. "
        "If SSE is not available, clients can poll GET /status/{check_id} instead."
    ),
    response_class=StreamingResponse,
)
async def stream_redirect_check(
    check_id: str,
    request: Request,
    redis: Redis | None = Depends(get_redis),
) -> StreamingResponse:
    if redis is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Redis is not available for streaming",
        )

    async def _generator():
        try:
            async for event in sse_event_stream(check_id, redis):
                if await request.is_disconnected():
                    return
                yield event
        except Exception as exc:
            logger.error("stream_redirect_check: error: %s", exc)
            error_event = {"event": "error", "data": {"error": str(exc)[:512]}}
            yield f"data: {json.dumps(error_event)}\n\n"

    return StreamingResponse(
        _generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get(
    "/result/{check_id}",
    response_model=RedirectCheckResultResponse,
    summary="Get completed redirect check results",
)
async def get_redirect_check_result(
    check_id: str,
    db: AsyncSession = Depends(get_db),
) -> RedirectCheckResultResponse:
    run = await _get_run_or_404(check_id, db)

    if run.status not in (StreamingAuditStatus.COMPLETED, StreamingAuditStatus.PARTIAL):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Redirect check is not completed yet (current status: '{run.status}')",
        )

    summary_data = run.final_summary or {}

    results_raw = summary_data.get("redirect_results", [])
    results: list[RedirectUrlResult] = [
        RedirectUrlResult(
            url=r.get("url", ""),
            redirect_count=r.get("redirect_count", 0) or len(r.get("hops", [])),
            final_url=r.get("final_url"),
            final_status=r.get("final_status"),
            error=r.get("error"),
            is_redirect=r.get("is_redirect", False),
            is_internal_redirect=r.get("is_internal_redirect", False),
            is_external_redirect=r.get("is_external_redirect", False),
            hops=[],
            chain=[],
        )
        for r in results_raw
    ]

    findings = [
        RedirectFinding(
            code=f.get("code", ""),
            severity=f.get("severity", "low"),
            status=f.get("status", "warning"),
            message=f.get("message", ""),
            evidence=f.get("evidence"),
            target_url=f.get("target_url", ""),
            redirect_count=f.get("redirect_count", 0),
            final_status=f.get("final_status"),
        )
        for f in summary_data.get("findings", [])
    ]

    recommendations_data = summary_data.get("recommendations", [])
    from app.modules.seprate_checks.redirect_check.schema import RedirectRecommendation

    recommendations = [
        RedirectRecommendation(
            code=r.get("code", ""),
            priority=r.get("priority", "low"),
            title=r.get("title", ""),
            message=r.get("message", ""),
            fix=r.get("fix", ""),
            where_to_fix=r.get("where_to_fix", "source_pages"),
            evidence=r.get("evidence"),
        )
        for r in recommendations_data
    ]

    summary = RedirectSummary(**summary_data.get("summary", {}))

    return RedirectCheckResultResponse(
        check_id=UUID(check_id),
        domain=run.domain,
        status=run.status,
        total_checked=len(results),
        results=results,
        findings=findings,
        recommendations=recommendations,
        summary=summary,
        overall_status=summary_data.get("overall_status"),
        severity=summary_data.get("severity"),
        cost_seconds=summary_data.get("cost_seconds"),
        checked_at=run.updated_at.isoformat() if run.updated_at else None,
    )
