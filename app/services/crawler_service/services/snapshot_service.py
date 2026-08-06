"""
Snapshot service - stores HTML snapshots.
Business logic for snapshot management.
"""
from typing import Optional
from uuid import UUID

from app.services.crawler_service.repositories.page_snapshot_repository import PageSnapshotRepository
from app.utils.crawler_utils.html_compressor import compress_html, should_compress
from app.models.crawler_models.page_snapshots import PageSnapshot


class SnapshotService:
    """Service for page snapshot operations."""

    def __init__(self, db):
        self.repository = PageSnapshotRepository(db)

    async def store_snapshot(
        self,
        page_id: UUID,
        html_content: str,
        compress: bool = True,
    ) -> PageSnapshot:
        """
        Store HTML snapshot for a page.

        Args:
            page_id: Page ID
            html_content: Raw HTML content
            compress: Whether to compress before storing

        Returns:
            PageSnapshot instance
        """
        content_to_store = html_content
        was_compressed = False

        if compress and should_compress(html_content):
            content_to_store = compress_html(html_content)
            was_compressed = True

        return await self.repository.save_snapshot(page_id, content_to_store, was_compressed)

    async def get_snapshot(self, page_id: UUID) -> Optional[PageSnapshot]:
        """Get snapshot for a page."""
        return await self.repository.get_by_page_id(page_id)

    async def delete_snapshot(self, page_id: UUID) -> bool:
        """Delete snapshot for a page."""
        return await self.repository.delete_by_page_id(page_id)
