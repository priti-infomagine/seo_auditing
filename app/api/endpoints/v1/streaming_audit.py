import asyncio
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.streaming_audit.models.streaming_audit_run import StreamingAuditRun
from app.modules.streaming_audit.repositories.streaming_audit_repository import StreamingAuditRepository
from app.modules.streaming_audit.schemas.streaming_audit_schemas import (
    StreamingAuditCreateRequest,
    StreamingAuditQueuedResponse,
    StreamingAuditStatusResponse,
)
from app.modules.streaming_audit.services.redis_scheduler import RedisQueueScheduler
from app.modules.streaming_audit.services.streaming_audit_service import StreamingAuditService, normalize_url
from app.shared.tasks.celery_app import celery_app

router = APIRouter()


@router.post(
    "/",
    response_model=StreamingAuditQueuedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Queue a streaming page-level SEO audit",
)
async def create_streaming_audit(
    body: StreamingAuditCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> StreamingAuditQueuedResponse:
    """Queue the experimental page-level streaming pipeline.

    This endpoint is intentionally isolated from the legacy audit/analyze route and
    uses its own task namespace and queue.
    """
    try:
        seed_url = normalize_url(str(body.url))
        if not seed_url:
            raise HTTPException(status_code=400, detail="A valid URL is required.")

        service = StreamingAuditService(db)
        audit_run = await service.create_run(
            seed_url=seed_url,
            max_pages=body.max_pages,
            max_depth=body.max_depth,
            concurrency=body.concurrency,
            browser_concurrency=body.browser_concurrency,
            request_timeout=body.request_timeout,
            config={
                "full_pipeline": body.full_pipeline,
                "browser_concurrency": body.browser_concurrency,
                "request_timeout": body.request_timeout,
            },
        )

        scheduler = RedisQueueScheduler()
        await scheduler.initialize_run(str(audit_run.id), seed_url, body.max_pages)

        async_result = await asyncio.to_thread(
            celery_app.send_task,
            "streaming_audit.process_page",
            args=[str(audit_run.id), seed_url, 0],
            kwargs={"max_pages": body.max_pages, "max_depth": body.max_depth},
            queue="streaming_audit",
        )

        return StreamingAuditQueuedResponse(
            success=True,
            status="queued",
            message="Streaming audit queued successfully",
            audit_id=str(audit_run.id),
            task_id=async_result.id,
            status_url=f"/api/v1/streaming-audit/{audit_run.id}/status",
            result_url=f"/api/v1/streaming-audit/{audit_run.id}/result",
        )
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - reserved for integration errors.
        raise HTTPException(status_code=500, detail=f"Failed to queue streaming audit: {exc}") from exc


@router.get("/{audit_id}/status", response_model=StreamingAuditStatusResponse)
async def get_streaming_audit_status(
    audit_id: str,
    db: AsyncSession = Depends(get_db),
) -> StreamingAuditStatusResponse:
    repository = StreamingAuditRepository(db)
    audit_run = await repository.get_by_id(audit_id)
    if audit_run is None:
        raise HTTPException(status_code=404, detail="Streaming audit not found")

    return StreamingAuditStatusResponse(
        audit_id=str(audit_run.id),
        status=audit_run.status,
        discovered_count=audit_run.discovered_count,
        queued_count=audit_run.queued_count,
        processing_count=audit_run.processing_count,
        completed_count=audit_run.completed_count,
        failed_count=audit_run.failed_count,
        summary=audit_run.final_summary,
    )


@router.get("/{audit_id}/result")
async def get_streaming_audit_result(
    audit_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    repository = StreamingAuditRepository(db)
    audit_run = await repository.get_by_id(audit_id)
    if audit_run is None:
        raise HTTPException(status_code=404, detail="Streaming audit not found")

    return {
        "audit_id": str(audit_run.id),
        "status": audit_run.status,
        "seed_url": audit_run.seed_url,
        "summary": audit_run.final_summary,
        "partial": audit_run.status in {"queued", "processing", "partial"},
        "page_results": [],
    }
