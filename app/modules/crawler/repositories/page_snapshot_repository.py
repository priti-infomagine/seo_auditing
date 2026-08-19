"""
PageSnapshot repository - database operations for storing HTML snapshots.
"""
from typing import Optional
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

    async def save_snapshot(
        self,
        page_id: UUID,
        html_content: str,
        compressed: bool = False,
    ) -> PageSnapshot:
        """Save or replace HTML snapshot for a page."""
        # Check for existing snapshot (unique constraint on page_id)
        existing = await self.get_by_page_id(page_id)
        if existing:
            existing.content = compress_html(html_content) if compressed else html_content
            existing.compressed = True if compressed else False
            await self.db.flush()
            await self.db.refresh(existing)
            return existing

        snapshot = PageSnapshot(
            page_id=page_id,
            content=compress_html(html_content) if compressed else html_content,
            compressed=True if compressed else False,
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
