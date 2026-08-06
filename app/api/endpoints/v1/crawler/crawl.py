"""
POST /crawler/crawl — Crawl a URL and save the data.

Takes a URL as input, crawls it using the crawler service,
and saves the data to storage with domain name and incremental test number.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.logger import logger
from app.modules.crawler.schemas.crawler_schemas import CrawlRequest, CrawlResponse
from app.modules.crawler.crawl_service import CrawlerService

router = APIRouter()

# import asyncio

# loop = asyncio.get_running_loop()
# print("====================================")
# print("=" * 60)
# print("Loop:", loop)
# print("Loop class:", loop.__class__)
# print("Loop module:", loop.__class__.__module__)
# print("=" * 60)

# print("====================================")
@router.post(
    "/crawl",
    response_model=CrawlResponse,
    status_code=200,
    summary="Crawl a URL and save data",
    description="Crawls the provided URL, extracts data, and saves it to storage folder with incremental test number",
)
async def crawl_url(
    body: CrawlRequest,
    db: AsyncSession = Depends(get_db),
) -> CrawlResponse:
    """
    Crawl a URL and save the data.
    
    Args:
        body: CrawlRequest containing URL to crawl
        db: Database session (required by architecture, though not used for crawl storage)
        
    Returns:
        CrawlResponse with crawl results and file path
        
    Raises:
        HTTPException: If crawl fails or URL is invalid
    """
    logger.info(f"POST /crawler/crawl - Crawl endpoint called for URL: {body.url}")
    
    try:
        # Initialize crawler service
        # Note: Using local storage (app/storage/crawler/) not database
        service = CrawlerService()
        
        # Perform crawl
        result = await service.crawl_url(str(body.url))
        
        logger.info(f"Crawl successful for URL: {body.url}")
        
        return CrawlResponse(
            success=True,
            message="Crawl completed successfully",
            url=result["url"],
            domain=result["domain"],
            test_number=result["test_number"],
            file_path=result["file_path"],
            crawled_at=result["crawled_at"],
            data=result.get("data")
        )
        
    except ValueError as e:
        # Invalid URL or validation error
        logger.warning(f"Invalid URL provided: {body.url} - {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid URL: {str(e)}"
        )
    except RuntimeError as e:
        # Crawl failed
        logger.error(f"Crawl failed for URL: {body.url} - {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Crawl failed: {str(e)}"
        )
    except Exception as e:
        # Unexpected error
        logger.error(f"Unexpected error during crawl for URL: {body.url}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred during crawling"
        )