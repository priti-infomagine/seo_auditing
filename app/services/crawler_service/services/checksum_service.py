"""
Checksum service - generates page checksums.
Business logic for checksum generation.
"""
import sys
from pathlib import Path
from typing import Optional
from uuid import UUID

from crawler_service.repositories.crawl_page_repository import CrawlPageRepository
from app.utils.crawler_utils.checksum import generate_checksum


class ChecksumService:
    """Service for checksum operations."""
    
    def __init__(self, db):
        self.repository = CrawlPageRepository(db)
    
    async def generate_and_save_checksum(
        self,
        page_id: UUID,
        content: bytes,
    ) -> Optional[str]:
        """
        Generate checksum for page content and save.
        
        Args:
            page_id: Page ID
            content: Page content bytes
            
        Returns:
            Checksum string or None if page not found
        """
        page = await self.repository.get_by_id(page_id)
        if not page:
            return None
        
        checksum = generate_checksum(content)
        page.checksum = checksum
        await self.repository.update(page)
        
        return checksum