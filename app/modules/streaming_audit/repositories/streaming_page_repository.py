from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.streaming_audit.models.streaming_page_result import StreamingPageResult


class StreamingPageRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_audit_and_url(self, audit_id: uuid.UUID | str, url: str) -> StreamingPageResult | None:
        stmt = select(StreamingPageResult).where(
            StreamingPageResult.audit_id == uuid.UUID(str(audit_id)),
            StreamingPageResult.normalized_url == url,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert(self, result: StreamingPageResult) -> StreamingPageResult:
        existing = await self.get_by_audit_and_url(result.audit_id, result.normalized_url)
        if existing is None:
            self.session.add(result)
        else:
            for column in [
                "canonical_url",
                "http_status",
                "processing_status",
                "page_score",
                "processing_latency_ms",
                "parsed_payload",
                "page_findings",
                "discovered_urls",
                "error_info",
                "last_error",
            ]:
                setattr(existing, column, getattr(result, column))
            result = existing
        await self.session.commit()
        await self.session.refresh(result)
        return result
