"""
Redirect service - stores redirect chains.
Business logic for redirect handling.
"""
import sys
from pathlib import Path
from typing import List
from uuid import UUID

from crawler_service.extractors.redirect_extractor import ExtractedRedirect
from crawler_service.repositories.crawl_page_repository import CrawlPageRepository

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.models.crawler_models.crawl_pages import CrawlPage


class RedirectService:
    """Service for redirect operations."""
    
    def __init__(self, db, page_id: UUID):
        self.repository = CrawlPageRepository(db)
        self.page_id = page_id
    
    async def process_and_save_redirects(
        self,
        redirects: List[ExtractedRedirect],
    ) -> None:
        """
        Process redirect chain and update final URL.
        
        Args:
            redirects: List of ExtractedRedirect objects
        """
        if not redirects:
            return
        
        # Get the final redirect URL
        final_redirect = redirects[-1]
        
        # Update the page with final URL if different
        page = await self.repository.get_by_id(self.page_id)
        if page and page.url != final_redirect.url:
            page.final_url = final_redirect.url
            await self.repository.update(page)