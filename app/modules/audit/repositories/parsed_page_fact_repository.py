"""
ParsedPageFact repository - database operations for ParsedPageFact model.

Provides upsert (insert-on-duplicate) for idempotency, ensuring no
duplicate parsed facts for the same (project_id, page_id).
"""
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.models.parsed_page_facts import ParsedPageFact


class ParsedPageFactRepository:
    """Repository for ParsedPageFact database operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def upsert(self, fact: ParsedPageFact) -> ParsedPageFact:
        """
        Insert or update a ParsedPageFact for (project_id, page_id).
        Checks for existing row; if found, updates it. Otherwise creates.
        """
        existing = await self.get_by_page_id(fact.project_id, fact.page_id)
        if existing:
            existing.url = fact.url
            existing.domain = fact.domain
            existing.parsed_data = fact.parsed_data
            existing.page_facts = fact.page_facts
            existing.elements = fact.elements
            existing.attributes = fact.attributes
            existing.parse_errors = fact.parse_errors
            existing.content_hash = fact.content_hash
            existing.parsed_at = fact.parsed_at
            self.db.add(existing)
            await self.db.flush()
            await self.db.refresh(existing)
            return existing
        return await self.create(fact)

    async def create(self, fact: ParsedPageFact) -> ParsedPageFact:
        """Create a new ParsedPageFact record."""
        self.db.add(fact)
        await self.db.flush()
        await self.db.refresh(fact)
        return fact

    async def bulk_upsert(self, facts: List[ParsedPageFact]) -> int:
        """
        Bulk insert or update ParsedPageFact rows.
        Returns the number of rows processed.
        """
        count = 0
        for fact in facts:
            if fact.parsed_data is None:
                continue
            existing = await self.get_by_page_id(fact.project_id, fact.page_id)
            if existing:
                existing.url = fact.url
                existing.domain = fact.domain
                existing.parsed_data = fact.parsed_data
                existing.page_facts = fact.page_facts
                existing.elements = fact.elements
                existing.attributes = fact.attributes
                existing.parse_errors = fact.parse_errors
                existing.content_hash = fact.content_hash
                existing.parsed_at = fact.parsed_at
                self.db.add(existing)
            else:
                self.db.add(fact)
            count += 1
        if count > 0:
            await self.db.flush()
        return count

    async def exists(self, project_id: UUID, page_id: UUID) -> bool:
        """Check if a parsed fact exists for this project+page."""
        result = await self.db.execute(
            select(ParsedPageFact.id).where(
                ParsedPageFact.project_id == project_id,
                ParsedPageFact.page_id == page_id,
            )
        )
        return result.scalar_one_or_none() is not None

    async def get_by_page_id(self, project_id: UUID, page_id: UUID) -> Optional[ParsedPageFact]:
        """Get parsed fact by page ID."""
        result = await self.db.execute(
            select(ParsedPageFact).where(
                ParsedPageFact.project_id == project_id,
                ParsedPageFact.page_id == page_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_by_project_id(self, project_id: UUID) -> List[ParsedPageFact]:
        """Get all parsed facts for a project."""
        result = await self.db.execute(
            select(ParsedPageFact).where(
                ParsedPageFact.project_id == project_id
            ).order_by(ParsedPageFact.parsed_at)
        )
        return list(result.scalars().all())

    async def get_by_crawl_id(self, crawl_id: UUID) -> List[ParsedPageFact]:
        """Get all parsed facts for a crawl."""
        result = await self.db.execute(
            select(ParsedPageFact).where(
                ParsedPageFact.crawl_id == crawl_id
            ).order_by(ParsedPageFact.parsed_at)
        )
        return list(result.scalars().all())

    async def delete_by_project_id(self, project_id: UUID) -> int:
        """Delete all parsed facts for a project. Returns count deleted."""
        result = await self.db.execute(
            delete(ParsedPageFact).where(
                ParsedPageFact.project_id == project_id
            )
        )
        return result.rowcount
