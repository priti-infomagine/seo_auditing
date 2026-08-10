"""
Page crawl service - orchestrates fetching and initial processing of a single page.

This service:
1. Receives a URL
2. Calls fetch_service
3. Handles fetch result
4. Extracts DocumentFacts
5. Returns PageCrawlResult

It does NOT:
- Parse HTML (that is the parser module)
- Extract SEO data (that is page_extraction_service)
- Write to PostgreSQL (that is crawl_persistence_service)
"""
from typing import Optional
from uuid import UUID

from app.modules.crawler.extractors.document_extractor import DocumentFacts, extract_document
from app.modules.crawler.services.fetch_service import FetchResult, fetch_page
from app.shared.utils.url_utils import normalize_url


class PageCrawlResult:
    """Structured result of crawling a single page."""

    def __init__(
        self,
        url: str,
        normalized_url: str,
        document: Optional[DocumentFacts] = None,
        fetch_result: Optional[FetchResult] = None,
        error: Optional[str] = None,
        error_type: Optional[str] = None,
    ):
        self.url = url
        self.normalized_url = normalized_url
        self.document = document
        self.fetch_result = fetch_result
        self.error = error
        self.error_type = error_type
        self.success = document is not None and fetch_result is not None and error is None


class PageCrawlService:
    """Service for crawling a single page."""

    async def crawl_page(
        self,
        url: str,
        timeout: int = 30,
        follow_redirects: bool = True,
        user_agent: Optional[str] = None,
        max_redirects: int = 10,
        max_retries: int = 3,
    ) -> PageCrawlResult:
        """
        Crawl a single page and return structured result.

        Args:
            url: URL to crawl
            timeout: Request timeout in seconds
            follow_redirects: Whether to follow redirects
            user_agent: User agent string
            max_redirects: Maximum redirects to follow
            max_retries: Maximum retry attempts

        Returns:
            PageCrawlResult with document facts or error
        """
        try:
            normalized_url = normalize_url(url)
        except Exception as exc:
            return PageCrawlResult(
                url=url,
                normalized_url=url,
                error=str(exc),
                error_type="invalid_url",
            )

        fetch_result = await fetch_page(
            normalized_url,
            timeout=timeout,
            follow_redirects=follow_redirects,
            user_agent=user_agent,
            max_redirects=max_redirects,
            max_retries=max_retries,
        )

        if fetch_result.error:
            return PageCrawlResult(
                url=url,
                normalized_url=normalized_url,
                fetch_result=fetch_result,
                error=fetch_result.error,
                error_type=fetch_result.error_type,
            )

        html_content = fetch_result.content.decode("utf-8", errors="ignore")
        document = extract_document(html_content, normalized_url)

        return PageCrawlResult(
            url=url,
            normalized_url=normalized_url,
            document=document,
            fetch_result=fetch_result,
        )
