"""
RedirectService - Process and persist HTTP redirect chains for crawler pages.
"""
from typing import Any, List
from uuid import UUID

from app.modules.crawler.models.crawl_pages import CrawlPage
from app.modules.crawler.models.page_links import PageLink
from app.modules.crawler.models.page_network_data import PageNetworkData
from app.modules.crawler.repositories.crawl_page_repository import CrawlPageRepository
from app.modules.crawler.repositories.page_link_repository import PageLinkRepository
from app.modules.crawler.repositories.page_network_data_repository import PageNetworkDataRepository


class RedirectService:
    """Service to process redirect chains and persist evidence."""

    def __init__(self, db, page_id: UUID):
        self.db = db
        self.page_id = page_id
        self.link_repo = PageLinkRepository(db)
        self.network_repo = PageNetworkDataRepository(db)
        self.page_repo = CrawlPageRepository(db)

    async def process_and_save_redirects(self, redirect_links: List[Any]) -> None:
        if not redirect_links:
            return

        valid_links = [r for r in redirect_links if isinstance(r, dict)]
        if not valid_links:
            return

        crawl_job_id = await self._get_crawl_job_id()
        if crawl_job_id is None:
            return

        link_objects = []
        for redirect in valid_links:
                link_objects.append(
                    PageLink(
                        page_id=self.page_id,
                        crawl_job_id=crawl_job_id,
                        target_url=redirect.get("url", ""),
                        normalized_target_url=redirect.get("url"),
                        anchor_text="",
                        rel="",
                        link_type="redirect",
                        is_internal=False,
                        is_external=True,
                        nofollow=False,
                        ugc=False,
                        sponsored=False,
                        is_crawlable=False,
                    )
                )

        if link_objects:
            await self.link_repo.create_batch(link_objects)

        network = await self.network_repo.get_by_page_id(self.page_id)
        if network:
            redirect_payload = [
                {"url": r.get("url", ""), "status_code": r.get("status_code", 0)}
                for r in redirect_links
                if isinstance(r, dict)
            ]
            network.redirects = redirect_payload
            await self.network_repo.update(network)

    async def _get_crawl_job_id(self) -> UUID | None:
        page = await self.page_repo.get_by_id(self.page_id)
        return page.crawl_job_id if page else None
