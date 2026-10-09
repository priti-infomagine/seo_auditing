from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Coroutine, TypeVar

from celery import shared_task
from sqlalchemy import case, update

from app.core.database import async_session_factory
from app.modules.streaming_audit.config import STREAMING_AUDIT_MAX_CONCURRENCY
from app.modules.streaming_audit.models.streaming_audit_run import StreamingAuditRun
from app.modules.streaming_audit.models.streaming_audit_run import StreamingAuditStatus
from app.modules.streaming_audit.services.page_processor import PageProcessor
from app.modules.streaming_audit.services.redis_scheduler import RedisQueueScheduler
from app.modules.streaming_audit.services.streaming_audit_service import StreamingAuditService, dedupe_urls, normalize_url
from app.shared.tasks.celery_app import celery_app

_worker_loop: asyncio.AbstractEventLoop | None = None
_worker_loop_pid: int | None = None
_Result = TypeVar("_Result")


def _run_on_worker_loop(coroutine: Coroutine[Any, Any, _Result]) -> _Result:
    """Run task coroutines on one event loop per worker process."""
    global _worker_loop, _worker_loop_pid

    current_pid = os.getpid()
    if _worker_loop is None or _worker_loop_pid != current_pid:
        _worker_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_worker_loop)
        _worker_loop_pid = current_pid

    return _worker_loop.run_until_complete(coroutine)


@shared_task(
    bind=True,
    name="streaming_audit.process_seed_url",
    queue="streaming_audit",
    max_retries=3,
    default_retry_delay=30,
    autoretry_for=(Exception,),
)
def process_seed_url(self, audit_id: str, url: str, max_depth: int = 2, depth: int = 0):
    """Backwards-compatible seed entry point for the streaming audit queue."""
    return process_page.apply_async(
        args=[audit_id, url, depth],
        kwargs={"max_pages": 100, "max_depth": max_depth},
        queue="streaming_audit",
    )


@shared_task(
    bind=True,
    name="streaming_audit.process_page",
    queue="streaming_audit",
    max_retries=3,
    default_retry_delay=30,
    autoretry_for=(Exception,),
)
def process_page(self, audit_id: str, url: str, depth: int = 0, max_pages: int = 100, max_depth: int = 3):
    """Process one URL in the streaming audit page-level lifecycle."""

    async def _run() -> dict:
        scheduler = RedisQueueScheduler()
        acquired = False
        normalized_url = normalize_url(url)
        try:
            acquired = await scheduler.reserve_slot(audit_id, limit=STREAMING_AUDIT_MAX_CONCURRENCY)
            if not acquired:
                celery_app.send_task(
                    "streaming_audit.process_page",
                    args=[audit_id, url, depth],
                    kwargs={"max_pages": max_pages, "max_depth": max_depth},
                    queue="streaming_audit",
                    countdown=1,
                )
                return {"audit_id": audit_id, "url": url, "status": "queued", "depth": depth, "page_score": 0}

            if not normalized_url:
                return {"audit_id": audit_id, "status": "failed", "url": url, "depth": depth}

            async with async_session_factory() as session:
                service = StreamingAuditService(session)
                run = await service.get_run(audit_id)
                if run is None:
                    return {"audit_id": audit_id, "status": "missing_audit", "url": url, "depth": depth}

                max_pages = run.max_pages
                max_depth = run.max_depth
                await session.execute(
                    update(StreamingAuditRun)
                    .where(StreamingAuditRun.id == uuid.UUID(str(audit_id)))
                    .values(
                        status=StreamingAuditStatus.PROCESSING,
                        processing_count=StreamingAuditRun.processing_count + 1,
                    )
                )
                await session.commit()

            try:
                processor = PageProcessor()
                page_result = await processor.process_page(str(audit_id), normalized_url, depth=depth)
            except Exception as exc:
                page_result = {
                    "audit_id": audit_id,
                    "url": normalized_url,
                    "normalized_url": normalized_url,
                    "status": "failed",
                    "error": str(exc),
                    "http_status": None,
                    "page_score": 0,
                    "discovered_urls": [],
                    "processing_latency_ms": 0,
                }

            filtered_children = []
            if depth < max_depth:
                filtered_children = await scheduler.enqueue_many(
                    audit_id,
                    (
                        child
                        for child in dedupe_urls(page_result.get("discovered_urls", []))
                        if normalize_url(child) != normalized_url
                    ),
                    depth=depth + 1,
                    max_pages=max_pages,
                )
                for child in filtered_children:
                    celery_app.send_task(
                        "streaming_audit.process_page",
                        args=[audit_id, child, depth + 1],
                        kwargs={"max_pages": max_pages, "max_depth": max_depth},
                        queue="streaming_audit",
                    )

            async with async_session_factory() as session:
                service = StreamingAuditService(session)
                await service.upsert_page_result(
                    audit_id=audit_id,
                    normalized_url=normalized_url,
                    canonical_url=page_result.get("canonical_url") or page_result.get("normalized_url") or normalized_url,
                    processing_status=page_result.get("status", "failed"),
                    http_status=page_result.get("http_status"),
                    page_score=page_result.get("page_score"),
                    processing_latency_ms=page_result.get("processing_latency_ms"),
                    parsed_payload=page_result.get("parsed_payload"),
                    page_findings={
                        "passed_checks": page_result.get("passed_checks", 0),
                        "failed_checks": page_result.get("failed_checks", 0),
                        "warnings": page_result.get("warnings", []),
                        "issues": page_result.get("issues", []),
                    },
                    discovered_urls=filtered_children,
                    error_info=page_result.get("error"),
                )
                successful = page_result.get("status") == "completed"
                finished_at = datetime.now(timezone.utc)
                completed_total = StreamingAuditRun.completed_count + (1 if successful else 0)
                failed_total = StreamingAuditRun.failed_count + (0 if successful else 1)
                complete = completed_total + failed_total >= StreamingAuditRun.max_pages
                values = {
                    "processing_count": case(
                        (StreamingAuditRun.processing_count > 0, StreamingAuditRun.processing_count - 1),
                        else_=0,
                    ),
                    "discovered_count": StreamingAuditRun.discovered_count + len(filtered_children),
                    "status": case(
                        (complete, StreamingAuditStatus.COMPLETED),
                        else_=StreamingAuditStatus.PARTIAL,
                    ),
                    "completed_at": case((complete, finished_at), else_=StreamingAuditRun.completed_at),
                }
                if successful:
                    values["completed_count"] = completed_total
                else:
                    values["failed_count"] = failed_total
                result = await session.execute(
                    update(StreamingAuditRun)
                    .where(StreamingAuditRun.id == uuid.UUID(str(audit_id)))
                    .values(**values)
                    .returning(StreamingAuditRun)
                )
                run = result.scalar_one()
                run.final_summary = {
                    "audit_id": audit_id,
                    "completed_count": run.completed_count,
                    "failed_count": run.failed_count,
                    "last_updated": finished_at.isoformat(),
                    "processed_url": normalized_url,
                    "discovered_urls": filtered_children,
                }
                await session.commit()

                return {
                    "audit_id": audit_id,
                    "url": normalized_url,
                    "status": run.status,
                    "page_score": page_result.get("page_score", 0),
                    "discovered_urls": filtered_children,
                    "depth": depth,
                    "processing_latency_ms": page_result.get("processing_latency_ms", 0),
                }
        finally:
            try:
                if acquired:
                    await scheduler.release_slot(audit_id)
            finally:
                await scheduler.close()

    try:
        return _run_on_worker_loop(_run())
    except Exception as exc:  # pragma: no cover
        raise self.retry(exc=exc)
