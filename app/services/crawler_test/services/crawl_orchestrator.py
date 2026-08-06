"""
Crawl orchestrator - controls the entire crawl lifecycle.
Orchestrates all services to perform a complete crawl.
"""
import sys
from pathlib import Path
from typing import Optional
from uuid import UUID

from crawler_test.extractors.asset_extractor import extract_assets
from crawler_test.extractors.link_extractor import extract_links
from crawler_test.repositories.crawl_job_repository import CrawlJobRepository
from crawler_test.services.asset_service import AssetService
from crawler_test.services.crawl_error_service import CrawlErrorService
from crawler_test.services.crawl_statistics_service import CrawlStatisticsService
from crawler_test.services.checksum_service import ChecksumService
from crawler_test.services.fetch_service import fetch_page, FetchResult
from crawler_test.services.link_service import LinkService
from crawler_test.services.page_service import PageService
from crawler_test.services.redirect_service import RedirectService
from crawler_test.services.response_service import process_response, ProcessedResponse
from crawler_test.services.snapshot_service import SnapshotService


class CrawlOrchestrator:
    """Orchestrates the entire crawl lifecycle."""
    
    def __init__(self, db, crawl_job_id: UUID):
        self.db = db
        self.crawl_job_id = crawl_job_id
        self.job_repository = CrawlJobRepository(db)
        self.page_service = PageService(db, crawl_job_id)
        self.link_service = None  # Initialized per page
        self.asset_service = None  # Initialized per page
        self.redirect_service = None  # Initialized per page
        self.snapshot_service = SnapshotService(db)
        self.error_service = CrawlErrorService(db)
        self.checksum_service = ChecksumService(db)
        self.statistics_service = CrawlStatisticsService(db)
    
    async def crawl_page(self, url: str, depth: int = 0, parent_page_id: Optional[UUID] = None) -> None:
        """
        Crawl a single page and process it.
        
        Args:
            url: URL to crawl
            depth: Current crawl depth
            parent_page_id: Parent page ID for hierarchy
        """
        try:
            # Fetch the page
            fetch_result = await fetch_page(url)
            
            if fetch_result.error:
                await self.error_service.log_error(
                    self.crawl_job_id,
                    parent_page_id,
                    "fetch_error",
                    fetch_result.error,
                )
                return
            
            # Process response
            processed = process_response(fetch_result)
            if not processed:
                return
            
            # Create or update page
            normalized_url = url.lower().strip()
            page = await self.page_service.create_or_update_page(
                url=url,
                normalized_url=normalized_url,
                metadata=processed.metadata,
                parent_page_id=parent_page_id,
                depth=depth,
            )
            
            # Initialize services for this page
            self.link_service = LinkService(self.db, page.id, url)
            self.asset_service = AssetService(self.db, page.id)
            self.redirect_service = RedirectService(self.db, page.id)
            
            # Store snapshot
            html_content = processed.content.decode('utf-8', errors='ignore')
            await self.snapshot_service.store_snapshot(page.id, html_content)
            
            # Generate checksum
            await self.checksum_service.generate_and_save_checksum(page.id, processed.content)
            
            # Process redirects
            # Note: Would need actual response object for full redirect chain
            # await self.redirect_service.process_and_save_redirects(redirects)
            
            # Extract and save links
            if processed.metadata.content_type == "text/html":
                extracted_links = extract_links(html_content, url)
                await self.link_service.process_and_save_links(extracted_links)
                
                # Extract and save assets
                extracted_assets = extract_assets(html_content, url)
                await self.asset_service.process_and_save_assets(extracted_assets)
        
        except Exception as e:
            await self.error_service.log_error(
                self.crawl_job_id,
                parent_page_id,
                "crawl_error",
                str(e),
            )
    
    async def get_summary(self) -> Optional[dict]:
        """Get crawl summary."""
        return await self.statistics_service.get_crawl_summary(self.crawl_job_id)