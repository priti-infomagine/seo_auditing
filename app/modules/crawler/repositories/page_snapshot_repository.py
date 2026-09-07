"""
PageSnapshot repository - database operations for storing HTML snapshots.
"""
from typing import Dict, List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.crawler.models.page_snapshots import PageSnapshot
from app.modules.crawler.models.crawl_pages import CrawlPage
from app.shared.utils.html_compressor import compress_html


class PageSnapshotRepository:
    """Repository for page snapshot operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_page_ids(self, page_ids: List[UUID]) -> Dict[UUID, PageSnapshot]:
        """
        Batch-fetch snapshots by page IDs in a single query.

        Returns a dict keyed by page_id for O(1) lookup, replacing per-page
        `get_by_page_id` loops (N+1) in the analysis pipeline.
        """
        if not page_ids:
            return {}
        out: Dict[UUID, PageSnapshot] = {}
        for start in range(0, len(page_ids), 1000):
            batch = page_ids[start : start + 1000]
            result = await self.db.execute(
                select(PageSnapshot).where(PageSnapshot.page_id.in_(batch))
            )
            for row in result.scalars().all():
                out[row.page_id] = row
        return out

    async def save_snapshot(
        self,
        page_id: UUID,
        html_content: str,
        compressed: bool = False,
        *,
        parsed_data: Optional[dict] = None,
    ) -> PageSnapshot:
        """Save or replace HTML snapshot for a page."""
        # Check for existing snapshot (unique constraint on page_id)
        existing = await self.get_by_page_id(page_id)
        if existing:
            existing.content = compress_html(html_content) if compressed else html_content
            existing.compressed = True if compressed else False
            if parsed_data is not None:
                existing.parsed_data = parsed_data
            await self.db.flush()
            await self.db.refresh(existing)
            return existing

        snapshot = PageSnapshot(
            page_id=page_id,
            content=compress_html(html_content) if compressed else html_content,
            compressed=True if compressed else False,
            parsed_data=parsed_data,
        )
        self.db.add(snapshot)
        await self.db.flush()
        await self.db.refresh(snapshot)
        return snapshot

    async def get_by_page_id(self, page_id: UUID) -> Optional[PageSnapshot]:
        """Get snapshot by page ID."""
        result = await self.db.execute(
            select(PageSnapshot).where(PageSnapshot.page_id == page_id)
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, page_id: UUID) -> Optional[CrawlPage]:
        """Get page by ID (kept for backward compatibility)."""
        result = await self.db.execute(
            select(CrawlPage).where(CrawlPage.id == page_id)
        )
        return result.scalar_one_or_none()

    async def delete_by_page_id(self, page_id: UUID) -> bool:
        """Delete snapshot for a page."""
        snapshot = await self.get_by_page_id(page_id)
        if snapshot:
            await self.db.delete(snapshot)
            return True
        return False
