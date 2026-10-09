from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .model import SchemaAudit, SchemaGeneration, GenerationStatus


class SchemaGenerationRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, generation: SchemaGeneration) -> SchemaGeneration:
        self.db.add(generation)
        await self.db.flush()
        await self.db.refresh(generation)
        return generation

    async def get(self, generation_id: UUID) -> Optional[SchemaGeneration]:
        result = await self.db.execute(
            select(SchemaGeneration).where(SchemaGeneration.id == generation_id)
        )
        return result.scalar_one_or_none()


class SchemaAuditRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, audit: SchemaAudit) -> SchemaAudit:
        self.db.add(audit)
        await self.db.flush()
        await self.db.refresh(audit)
        return audit

    async def get(self, audit_id: UUID) -> Optional[SchemaAudit]:
        result = await self.db.execute(
            select(SchemaAudit).where(SchemaAudit.id == audit_id)
        )
        return result.scalar_one_or_none()