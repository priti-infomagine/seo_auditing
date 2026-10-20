from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.logger import logger
from app.shared.tasks.celery_app import celery_app

from .model import RedirectUrlAudit
from .repository import RedirectUrlAuditRepository
from .schema import (
    RedirectCheckQueuedResponse,
    RedirectCheckResultResponse,
    RedirectCheckStatusResponse,
    RedirectUrlCheckRequest,
)
from .service import RedirectUrlAuditService

router = APIRouter()
TERMINAL_STATUSES = {"completed", "partial", "failed"}


async def _get_audit_or_404(check_id: str, db: AsyncSession) -> RedirectUrlAudit:
    try:
        parsed_id = UUID(check_id)
    except (ValueError, AttributeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid check ID format (must be a valid UUID)",
        ) from exc

    audit = await RedirectUrlAuditRepository(db).get(parsed_id)
    if audit is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Redirect URL audit '{check_id}' was not found",
        )
    return audit


def _status_response(audit: RedirectUrlAudit) -> RedirectCheckStatusResponse:
    return RedirectCheckStatusResponse(
        check_id=audit.id,
        domain=audit.domain,
        status=audit.status,
        progress=audit.progress or {},
        discovered_count=audit.discovered_count,
        completed_count=audit.completed_count,
        failed_count=audit.failed_count,
        max_depth=audit.max_depth,
        max_hops=audit.max_hops,
        error=audit.error_info,
    )


@router.post(
    "/check",
    response_model=RedirectCheckQueuedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Queue a redirect URL audit",
    description="Discovers pages, checks redirect chains, and builds a URL graph on the crawler queue.",
)
async def queue_redirect_url_audit(
    body: RedirectUrlCheckRequest,
    db: AsyncSession = Depends(get_db),
) -> RedirectCheckQueuedResponse:
    audit_id = uuid4()
    repository = RedirectUrlAuditRepository(db)
    audit = await repository.create(
        audit_id=audit_id,
        domain=body.domain,
        max_urls=body.max_urls,
        max_depth=body.max_depth,
        max_hops=body.max_hops,
    )
    try:
        task = await asyncio.to_thread(
            celery_app.send_task,
            "redirect_check.run_domain_check",
            args=[
                str(audit_id),
                body.domain,
                body.max_urls,
                body.max_depth,
                body.max_hops,
            ],
            queue="crawler",
        )
    except Exception as exc:
        await repository.update(
            audit_id,
            status="failed",
            error_info="The redirect audit could not be queued.",
            progress={"phase": "queue_failed"},
            completed_at=datetime.now(timezone.utc),
        )
        logger.exception("Could not queue redirect URL audit %s", audit_id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to queue redirect URL audit.",
        ) from exc

    return RedirectCheckQueuedResponse(
        check_id=audit.id,
        task_id=task.id,
        domain=audit.domain,
        max_urls=audit.max_urls,
        max_depth=audit.max_depth,
        max_hops=audit.max_hops,
        status_url=f"/api/v1/redirect-check/status/{audit_id}",
        stream_url=f"/api/v1/redirect-check/stream/{audit_id}",
    )


@router.get(
    "/status/{check_id}",
    response_model=RedirectCheckStatusResponse,
    summary="Get redirect URL audit progress",
)
async def get_redirect_url_audit_status(
    check_id: str,
    db: AsyncSession = Depends(get_db),
) -> RedirectCheckStatusResponse:
    return _status_response(await _get_audit_or_404(check_id, db))


@router.get(
    "/result/{check_id}",
    response_model=RedirectCheckResultResponse,
    summary="Get redirect URL audit results and graph",
)
async def get_redirect_url_audit_result(
    check_id: str,
    db: AsyncSession = Depends(get_db),
) -> RedirectCheckResultResponse:
    audit = await _get_audit_or_404(check_id, db)
    if audit.result is None and audit.status not in TERMINAL_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Redirect URL audit is not complete (current status: '{audit.status}')",
        )
    return RedirectCheckResultResponse.model_validate(
        await RedirectUrlAuditService(db).build_result(audit)
    )


@router.get(
    "/stream/{check_id}",
    summary="Stream redirect URL audit progress using server-sent events",
    response_class=StreamingResponse,
)
async def stream_redirect_url_audit(
    check_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    audit = await _get_audit_or_404(check_id, db)

    async def event_stream():
        previous: tuple[str, str] | None = None
        while not await request.is_disconnected():
            await db.refresh(audit)
            progress_json = json.dumps(audit.progress or {}, sort_keys=True)
            snapshot = (audit.status, progress_json)
            if snapshot != previous:
                payload: dict[str, Any] = {
                    "event": "progress",
                    "data": _status_response(audit).model_dump(mode="json"),
                }
                yield f"data: {json.dumps(payload)}\n\n"
                previous = snapshot
            if audit.status in TERMINAL_STATUSES:
                result = await RedirectUrlAuditService(db).build_result(audit)
                if result:
                    yield f"data: {json.dumps({'event': 'completed', 'data': result})}\n\n"
                return
            yield ": keep-alive\n\n"
            await asyncio.sleep(1)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
