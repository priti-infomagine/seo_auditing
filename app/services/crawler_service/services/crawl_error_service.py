"""
Crawl error service - handles errors and retries.
Business logic for error management.
"""
import sys
from pathlib import Path
from typing import List, Optional
from uuid import UUID

from crawler_service.repositories.crawl_error_repository import CrawlErrorRepository

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.models.crawler_models.crawl_errors import CrawlError


class CrawlErrorService:
    """Service for crawl error operations."""
    
    def __init__(self, db):
        self.repository = CrawlErrorRepository(db)
    
    async def log_error(
        self,
        crawl_id: UUID,
        page_id: Optional[UUID],
        error_type: str,
        error_message: str,
    ) -> CrawlError:
        """
        Log a crawl error.
        
        Args:
            crawl_id: Crawl job ID
            page_id: Page ID (optional)
            error_type: Type of error
            error_message: Error message
            
        Returns:
            Created CrawlError instance
        """
        error = CrawlError(
            crawl_id=crawl_id,
            page_id=page_id,
            error_type=error_type,
            error_message=error_message,
        )
        return await self.repository.create(error)
    
    async def get_errors(self, crawl_id: UUID) -> List[CrawlError]:
        """Get all errors for a crawl job."""
        return await self.repository.get_by_crawl_id(crawl_id)