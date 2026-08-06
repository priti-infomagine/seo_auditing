"""
Link service - validates and persists links.
Business logic + validation + persistence coordination.
"""
from typing import List
from uuid import UUID

from app.services.crawler_service.extractors.link_extractor import ExtractedLink
from app.services.crawler_service.repositories.page_link_repository import PageLinkRepository
from app.utils.crawler_utils.url_utils import is_internal_link, normalize_url
from app.models.crawler_models.page_links import PageLink


class LinkService:
    """Service for link operations."""

    def __init__(self, db, page_id: UUID, base_url: str):
        self.repository = PageLinkRepository(db)
        self.page_id = page_id
        self.base_url = base_url

    async def process_and_save_links(
        self,
        extracted_links: List[ExtractedLink],
    ) -> List[PageLink]:
        """
        Process extracted links and save to database.

        Args:
            extracted_links: List of ExtractedLink objects

        Returns:
            List of saved PageLink instances
        """
        saved_links = []

        for link in extracted_links:
            # Validate URL
            if not link.url:
                continue

            # Normalize URL
            normalized_url = normalize_url(link.url)

            # Determine if internal
            is_internal = is_internal_link(self.base_url, link.url)

            # Determine if nofollow
            is_nofollow = link.rel == "nofollow" if link.rel else False

            # Create PageLink
            page_link = PageLink(
                page_id=self.page_id,
                target_url=normalized_url,
                anchor_text=link.anchor_text,
                rel=link.rel,
                is_internal=is_internal,
                is_nofollow=is_nofollow,
                link_type=link.link_type,
            )

            saved_link = await self.repository.create(page_link)
            saved_links.append(saved_link)

        return saved_links
