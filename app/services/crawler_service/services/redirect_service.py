"""
Redirect service - stores redirect chains.
Business logic for redirect handling.
"""
from typing import List
from uuid import UUID

from app.services.crawler_service.extractors.redirect_extractor import ExtractedRedirect
from app.services.crawler_service.repositories.crawl_page_repository import CrawlPageRepository
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

    async def save_redirect_chain(
        self,
        redirect_response,
    ) -> List[ExtractedRedirect]:
        """
        Extract and process the redirect chain from an httpx response.

        Args:
            redirect_response: httpx.Response object (with .history)

        Returns:
            List of ExtractedRedirect objects
        """
        from app.services.crawler_service.extractors.redirect_extractor import (
            extract_redirect_chain,
        )

        redirects = extract_redirect_chain(redirect_response)
        await self.process_and_save_redirects(redirects)
        return redirects
