from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any, Iterable
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.streaming_audit.models.streaming_audit_run import StreamingAuditRun, StreamingAuditStatus
from app.modules.streaming_audit.models.streaming_page_result import StreamingPageResult


def normalize_url(value: str) -> str:
    """Normalize a URL for deduplication and scheduling.

    This is intentionally conservative and avoids rewriting the production
    crawler URL utilities; it only provides a minimal, safe normalization for
    the experiment.
    """
    if not value:
        return value

    candidate = value.strip()
    if not candidate:
        return candidate

    try:
        split = urlsplit(candidate)
    except ValueError:
        return candidate

    scheme = (split.scheme or "https").lower()
    netloc = split.netloc.lower()
    hostname = split.hostname or ""
    if hostname:
        hostname = hostname.lower().lstrip("www.")
        port = split.port
        netloc = hostname if port is None or port in (80, 443) else f"{hostname}:{port}"

    path = split.path or "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")

    query = split.query
    if query:
        query = "&".join(sorted(part for part in query.split("&") if part))

    normalized = urlunsplit((scheme, netloc, path, query, ""))
    return normalized


def dedupe_urls(urls: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in urls:
        normalized = normalize_url(value)
        if normalized and normalized not in seen:
            seen.add(normalized)
            ordered.append(normalized)
    return ordered


class StreamingAuditService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_run(
        self,
        *,
        seed_url: str,
        user_id: str | None = None,
        max_pages: int = 100,
        max_depth: int = 3,
        concurrency: int = 5,
        browser_concurrency: int = 2,
        request_timeout: float = 30.0,
        config: dict[str, Any] | None = None,
    ) -> StreamingAuditRun:
        normalized_seed = normalize_url(seed_url)
        domain = ""
        try:
            parts = urlsplit(normalized_seed)
            domain = parts.netloc or parts.path
        except Exception:
            domain = normalized_seed

        run = StreamingAuditRun(
            id=uuid.uuid4(),
            user_id=uuid.UUID(str(user_id)) if user_id else None,
            seed_url=normalized_seed,
            domain=domain,
            status=StreamingAuditStatus.QUEUED,
            max_pages=max_pages,
            max_depth=max_depth,
            concurrency=concurrency,
            browser_concurrency=browser_concurrency,
            request_timeout=int(request_timeout),
            config=config or {},
            started_at=datetime.now(timezone.utc),
        )
        self.session.add(run)
        await self.session.commit()
        await self.session.refresh(run)
        return run

    async def get_run(self, audit_id: uuid.UUID | str) -> StreamingAuditRun | None:
        stmt = select(StreamingAuditRun).where(StreamingAuditRun.id == uuid.UUID(str(audit_id)))
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def update_run(self, audit_id: uuid.UUID | str, **values: Any) -> StreamingAuditRun | None:
        run = await self.get_run(audit_id)
        if run is None:
            return None
        for key, value in values.items():
            if hasattr(run, key):
                setattr(run, key, value)
        await self.session.commit()
        await self.session.refresh(run)
        return run

    async def upsert_page_result(
        self,
        *,
        audit_id: uuid.UUID | str,
        normalized_url: str,
        canonical_url: str | None,
        processing_status: str,
        http_status: int | None,
        page_score: float | None,
        processing_latency_ms: int | None,
        parsed_payload: dict[str, Any] | None,
        page_findings: dict[str, Any] | None,
        discovered_urls: list[str] | None,
        error_info: str | None,
    ) -> StreamingPageResult:
        normalized = normalize_url(normalized_url)
        audit_uuid = uuid.UUID(str(audit_id))
        values = {
            "id": uuid.uuid4(),
            "audit_id": audit_uuid,
            "normalized_url": normalized,
            "canonical_url": canonical_url,
            "http_status": http_status,
            "processing_status": processing_status,
            "page_score": page_score,
            "processing_latency_ms": processing_latency_ms,
            "parsed_payload": parsed_payload,
            "page_findings": page_findings,
            "discovered_urls": discovered_urls,
            "error_info": error_info,
        }
        insert_statement = pg_insert(StreamingPageResult).values(**values)
        statement = (
            insert_statement.on_conflict_do_update(
                constraint="uq_streaming_page_result_audit_url",
                set_={
                    **{
                        key: value
                        for key, value in values.items()
                        if key not in {"id", "audit_id", "normalized_url"}
                    },
                    "updated_at": func.now(),
                },
            )
            .returning(StreamingPageResult)
        )
        result = await self.session.execute(statement)
        record = result.scalar_one()

        await self.session.commit()
        await self.session.refresh(record)
        return record

    async def get_run_pages(self, audit_id: uuid.UUID | str) -> list[StreamingPageResult]:
        stmt = select(StreamingPageResult).where(StreamingPageResult.audit_id == uuid.UUID(str(audit_id)))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_page_count(self, audit_id: uuid.UUID | str) -> int:
        return len(await self.get_run_pages(audit_id))

    async def ensure_completion(self, audit_id: uuid.UUID | str) -> StreamingAuditRun | None:
        run = await self.get_run(audit_id)
        if run is None:
            return None

        if run.status in {StreamingAuditStatus.COMPLETED, StreamingAuditStatus.FAILED, StreamingAuditStatus.CANCELLED}:
            return run

        total_page_count = await self.get_page_count(audit_id)
        if run.completed_count + run.failed_count >= total_page_count and total_page_count > 0:
            run.status = StreamingAuditStatus.COMPLETED
            run.completed_at = datetime.now(timezone.utc)
            run.final_summary = {
                "total_pages": total_page_count,
                "completed_count": run.completed_count,
                "failed_count": run.failed_count,
            }
            await self.session.commit()
            await self.session.refresh(run)
        return run
