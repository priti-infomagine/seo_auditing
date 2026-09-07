"""
GET /crawler/status/{crawl_id} — Get crawl job status.

Returns the current status and summary of a crawl job.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.core.database import get_db
from app.core.logger import logger
from app.modules.crawler.models.crawl_jobs import CrawlJob
from app.modules.crawler.models.crawl_pages import CrawlPage
from app.modules.crawler.models.crawl_errors import CrawlError
from app.modules.crawler.schemas.crawler_schemas import CrawlStatusResponse
from uuid import UUID

router = APIRouter()


@router.get(
    "/status/{crawl_id}",
    response_model=CrawlStatusResponse,
    summary="Get crawl job status",
    description="Returns the current status and summary of a crawl job",
)
async def get_crawl_status(
    crawl_id: str,
    db: AsyncSession = Depends(get_db),
) -> CrawlStatusResponse:
    """
    Get the status of a crawl job.
    
    Args:
        crawl_id: UUID of the crawl job
        db: Database session
        
    Returns:
        CrawlStatusResponse with job status and summary
        
    Raises:
        HTTPException: If crawl job not found
    """
    logger.info(f"GET /crawler/status/{crawl_id} - Status endpoint called")
    
    try:
        crawl_uuid = UUID(crawl_id)
        
        # Get crawl job
        result = await db.execute(
            select(CrawlJob).where(CrawlJob.id == crawl_uuid)
        )
        job = result.scalar_one_or_none()
        
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Crawl job {crawl_id} not found"
            )
        
        # Get pages count
        pages_result = await db.execute(
            select(func.count())
            .select_from(CrawlPage)
            .where(CrawlPage.crawl_id == crawl_uuid)
        )
        pages_count = pages_result.scalar_one()
        
        # Get errors count
        errors_result = await db.execute(
            select(func.count())
            .select_from(CrawlError)
            .where(CrawlError.crawl_id == crawl_uuid)
        )
        errors_count = errors_result.scalar_one()
        
        return CrawlStatusResponse(
            crawl_id=str(job.id),
            status=job.status,
            domain=job.domain,
            url=job.url,
            error=job.error,
            started_at=job.started_at.isoformat() if job.started_at else None,
            completed_at=job.completed_at.isoformat() if job.completed_at else None,
            duration_ms=job.duration_ms,
            pages_crawled=pages_count,
            pages_discovered=job.pages_discovered,
            pages_failed=job.pages_failed,
            total_pages=job.total_pages,
            current_page=job.current_page,
            progress_percent=job.progress_percent,
            total_errors=errors_count,
        )
        
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid crawl ID format: {crawl_id}"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching crawl status for {crawl_id}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while fetching crawl status"
        )
