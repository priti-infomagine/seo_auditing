"""
ParsedPageFact repository - database operations for ParsedPageFact model.

Provides upsert (insert-on-duplicate) for idempotency, ensuring no
duplicate parsed facts for the same (project_id, page_id).
"""
from typing import List, Optional, Set, Dict
from uuid import UUID

from sqlalchemy import select, delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
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

    async def get_existing_page_ids(
        self, project_id: UUID, page_ids: List[UUID]
    ) -> Set[UUID]:
        """
        Return the set of page_ids (within a project) that already have a
        parsed fact. Single query — replaces per-page `exists()` loops (N+1)
        in the parse stage.
        """
        if not page_ids:
            return set()
        rows = await self.db.execute(
            select(ParsedPageFact.page_id).where(
                ParsedPageFact.project_id == project_id,
                ParsedPageFact.page_id.in_(page_ids),
            )
        )
        return {row[0] for row in rows.all()}

    async def bulk_upsert(self, facts: List[ParsedPageFact]) -> int:
        """
        True bulk upsert of ParsedPageFact rows in batched statements.

        Uses PostgreSQL `INSERT ... ON CONFLICT (project_id, page_id)
        DO UPDATE`. The unique index `ix_parsed_page_facts_project_page`
        backs the conflict target (see alembic migration
        e5f6a7b8c9d0). Replaces the previous per-row SELECT+UPDATE loop.

        Batches inserts to stay under PostgreSQL's 32767 parameter limit
        (each row has 13 columns; max ~2520 rows per batch).

        Returns the number of rows processed.
        """
        if not facts:
            return 0

        # Each row has 13 columns; PostgreSQL max is 32767 parameters.
        # Use 500 rows per batch = 6500 params (well under the limit).
        BATCH_SIZE = 500
        total_processed = 0

        for start in range(0, len(facts), BATCH_SIZE):
            batch = facts[start : start + BATCH_SIZE]
            rows = []
            for fact in batch:
                if fact.parsed_data is None:
                    continue
                rows.append({
                    "id": fact.id,
                    "project_id": fact.project_id,
                    "crawl_id": fact.crawl_id,
                    "page_id": fact.page_id,
                    "url": fact.url,
                    "domain": fact.domain,
                    "parsed_data": fact.parsed_data,
                    "page_facts": fact.page_facts,
                    "elements": fact.elements,
                    "attributes": fact.attributes,
                    "parse_errors": fact.parse_errors,
                    "content_hash": fact.content_hash,
                    "parsed_at": fact.parsed_at,
                })
            if not rows:
                continue

            stmt = pg_insert(ParsedPageFact).values(rows)
            stmt = stmt.on_conflict_do_update(
                index_elements=["project_id", "page_id"],
                set_={
                    "url": stmt.excluded.url,
                    "domain": stmt.excluded.domain,
                    "parsed_data": stmt.excluded.parsed_data,
                    "page_facts": stmt.excluded.page_facts,
                    "elements": stmt.excluded.elements,
                    "attributes": stmt.excluded.attributes,
                    "parse_errors": stmt.excluded.parse_errors,
                    "content_hash": stmt.excluded.content_hash,
                    "parsed_at": stmt.excluded.parsed_at,
                },
            )
            await self.db.execute(stmt)
            await self.db.flush()
            total_processed += len(rows)

        return total_processed

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

    async def get_by_page_ids(self, page_ids: List) -> Dict:
        """
        Batch-fetch parsed facts by page IDs — additive to ``get_by_page_id``.

        Returns a dict keyed by ``page_id`` for O(1) lookup. Used by the new
        audit read layer's evidence endpoint to avoid per-page N+1 queries.
        """
        if not page_ids:
            return {}
        out: Dict = {}
        for start in range(0, len(page_ids), 1000):
            batch = page_ids[start : start + 1000]
            result = await self.db.execute(
                select(ParsedPageFact).where(ParsedPageFact.page_id.in_(batch))
            )
            for row in result.scalars().all():
                out[row.page_id] = row
        return out

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
