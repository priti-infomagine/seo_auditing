"""
POST /crawler/crawl — Queue a URL for crawling.

Takes a URL as input, creates a crawl job in the database,
and enqueues a Celery task to perform the crawl asynchronously.
Returns immediately with a crawl_id for status polling.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.logger import logger
from app.core.security import get_current_user
from app.modules.crawler.models.crawl_jobs import CrawlJob
from app.modules.crawler.repositories.crawl_job_repository import CrawlJobRepository
from app.modules.crawler.schemas.crawler_schemas import CrawlRequest, CrawlResponse
from app.modules.auth.models.users import User
from app.shared.tasks.celery_app import celery_app
from app.shared.utils.url_utils import get_domain
from uuid import uuid4

router = APIRouter()


@router.post(
    "/crawl",
    response_model=CrawlResponse,
    status_code=202,
    summary="Queue a URL for crawling",
    description="Creates a crawl job and enqueues it for background processing. Returns crawl_id immediately.",
)
async def crawl_url(
    body: CrawlRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CrawlResponse:
    """
    Queue a URL for crawling.

    Args:
        body: CrawlRequest containing URL to crawl
        db: Database session
        current_user: Authenticated user (injected by get_current_user)

    Returns:
        CrawlResponse with crawl_id and status

    Raises:
        HTTPException: If URL is invalid or user is not authenticated
    """
    logger.info(f"POST /crawler/crawl - Queuing crawl for URL: {body.url}")

    try:
        url_str = str(body.url)
        domain = get_domain(url_str)
        user_id = current_user.id

        crawl_config = {
            "max_depth": body.max_depth,
            "max_pages": body.max_pages,
            "concurrency": body.concurrency,
            "request_timeout": 30,
            "delay_ms": 0,
            "follow_redirects": True,
            "respect_robots": True,
        }

        # Create crawl job with config embedded as JSONB
        crawl_job = CrawlJob(
            id=uuid4(),
            user_id=user_id,
            url=url_str,
            domain=domain,
            status="queued",
            crawl_config=crawl_config,
        )
        job_repo = CrawlJobRepository(db)
        await job_repo.create(crawl_job)

        # Enqueue Celery task
        celery_app.send_task(
            "crawler.crawl_website",
            args=[str(crawl_job.id), url_str, str(crawl_job.user_id)],
        )

        logger.info(f"Crawl job queued: {crawl_job.id} for URL: {body.url}")

        return CrawlResponse(
            crawl_id=str(crawl_job.id),
            status="queued",
            message="Crawl job queued successfully",
        )

    except ValueError as e:
        logger.warning(f"Invalid URL provided: {body.url} - {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid URL: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Unexpected error queuing crawl for URL: {body.url}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while queuing crawl job"
        )
