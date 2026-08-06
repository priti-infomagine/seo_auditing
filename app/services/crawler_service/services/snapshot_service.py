"""
Snapshot service - stores HTML snapshots.
Business logic for snapshot management.
"""
from typing import Optional
from uuid import UUID

from crawler_service.repositories.page_snapshot_repository import PageSnapshotRepository
from app.utils.crawler_utils.html_compressor import compress_html, should_compress


class SnapshotService:
    """Service for page snapshot operations."""
    
    def __init__(self, db):
        self.repository = PageSnapshotRepository(db)
    
    async def store_snapshot(
        self,
        page_id: UUID,
        html_content: str,
        compress: bool = True,
    ) -> None:
        """
        Store HTML snapshot for a page.
        
        Args:
            page_id: Page ID
            html_content: Raw HTML content
            compress: Whether to compress before storing
        """
        content_to_store = html_content
        
        if compress and should_compress(html_content):
            content_to_store = compress_html(html_content)
        
        await self.repository.save_snapshot(page_id, content_to_store)
    
    async def get_snapshot(self, page_id: UUID) -> Optional[str]:
        """Get snapshot for a page."""
        page = await self.repository.get_by_id(page_id)
        return page if page else None