from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.streaming_audit.models.streaming_audit_run import StreamingAuditRun


class StreamingAuditRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, audit_run: StreamingAuditRun) -> StreamingAuditRun:
        self.session.add(audit_run)
        await self.session.commit()
        await self.session.refresh(audit_run)
        return audit_run

    async def get_by_id(self, audit_id: uuid.UUID | str) -> StreamingAuditRun | None:
        stmt = select(StreamingAuditRun).where(StreamingAuditRun.id == uuid.UUID(str(audit_id)))
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def update(self, audit_run: StreamingAuditRun, **values: Any) -> StreamingAuditRun:
        for key, value in values.items():
            if hasattr(audit_run, key):
                setattr(audit_run, key, value)
        await self.session.commit()
        await self.session.refresh(audit_run)
        return audit_run
