"""
POST /test-crawler - Synchronous test crawl endpoint.

Runs a full crawl inline (no Celery task queue) and returns complete
results directly in the API response. Intended for testing and debugging.
"""
from datetime import timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.datetime_utils import utc_now
from app.core.logger import logger
from app.core.security import get_current_user
from app.modules.crawler.models.crawl_jobs import CrawlJob
from app.modules.crawler.models.crawl_pages import CrawlPage
from app.modules.crawler.models.crawl_errors import CrawlError
from app.modules.crawler.models.page_links import PageLink
from app.modules.crawler.repositories.crawl_job_repository import CrawlJobRepository
from app.modules.crawler.repositories.crawl_page_repository import CrawlPageRepository
from app.modules.crawler.repositories.crawl_error_repository import CrawlErrorRepository
from app.modules.crawler.repositories.page_link_repository import PageLinkRepository
from app.modules.crawler.schemas.crawler_schemas import CrawlRequest, TestCrawlResponse
from app.modules.crawler.services.crawl_orchestrator import CrawlOrchestrator
from app.modules.auth.models.users import User
from app.shared.utils.url_utils import get_domain

router = APIRouter()


@router.post(
    "/test-crawler",
    response_model=TestCrawlResponse,
    status_code=200,
    summary="Run a synchronous test crawl",
    description="Runs a full crawl inline without a background task and returns complete results. For testing and debugging only.",
)
async def test_crawl_url(
    body: CrawlRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TestCrawlResponse:
    """
    Queue and run a crawl synchronously, returning full results.

    Args:
        body: CrawlRequest containing URL and crawl parameters
        db: Database session
        current_user: Authenticated user

    Returns:
        TestCrawlResponse with complete crawl results
    """
    logger.info(f"POST /crawler/test-crawler - Running synchronous crawl for URL: {body.url}")

    try:
        url_str = str(body.url)
        domain = get_domain(url_str)

        crawl_config = {
            "max_depth": body.max_depth,
            "max_pages": body.max_pages,
            "concurrency": body.concurrency,
            "request_timeout": 30,
            "delay_ms": 0,
            "follow_redirects": True,
            "respect_robots": True,
        }

        crawl_job = CrawlJob(
            id=uuid4(),
            user_id=current_user.id,
            url=url_str,
            domain=domain,
            status="queued",
            crawl_config=crawl_config,
        )
        job_repo = CrawlJobRepository(db)
        await job_repo.create(crawl_job)

        try:
            orchestrator = CrawlOrchestrator(db, crawl_job.id)
            await orchestrator.run(
                start_url=url_str,
                max_depth=body.max_depth,
                max_pages=body.max_pages,
                concurrency=body.concurrency,
            )
        except Exception as exc:
            logger.error(f"Synchronous crawl failed for {url_str}: {exc}", exc_info=True)
            job = await job_repo.get_by_id(crawl_job.id)
            if job and job.status not in ("completed", "failed", "cancelled"):
                job.status = "failed"
                job.error = str(exc)[:1024]
                job.completed_at = utc_now()
                await job_repo.update(job)

        job = await job_repo.get_by_id(crawl_job.id)
        if job:
            await db.refresh(job)

        page_repo = CrawlPageRepository(db)
        pages = await page_repo.get_by_crawl_id(crawl_job.id)

        error_repo = CrawlErrorRepository(db)
        errors = await error_repo.get_by_crawl_id(crawl_job.id)

        link_repo = PageLinkRepository(db)
        all_links = await link_repo.get_by_crawl_job_id(crawl_job.id)
        links_by_page: dict[str, list[dict]] = {}
        for link in all_links:
            links_by_page.setdefault(str(link.page_id), []).append({
                "target_url": link.target_url,
                "anchor_text": link.anchor_text or "",
                "rel": link.rel or "",
                "link_type": link.link_type,
                "is_internal": link.is_internal,
                "is_external": link.is_external,
                "nofollow": link.nofollow,
                "ugc": link.ugc,
                "sponsored": link.sponsored,
            })

        page_list = []
        for page in pages:
            page_list.append({
                "url": page.url,
                "normalized_url": page.normalized_url,
                "status_code": page.status_code or 0,
                "content_type": page.content_type or "",
                "content_length": page.content_length or 0,
                "response_time_ms": page.response_time_ms or 0,
                "depth": page.depth,
                "is_redirect": page.is_redirect,
                "is_success": page.is_success,
                "is_error": page.is_error,
                "links": links_by_page.get(str(page.id), []),
            })

        error_list = [
            {
                "error_type": e.error_type,
                "error_message": e.error_message,
            }
            for e in errors
        ]

        return TestCrawlResponse(
            success=job.status == "completed" if job else False,
            crawl_id=str(crawl_job.id),
            status=job.status if job else "failed",
            url=job.url if job else url_str,
            domain=job.domain if job else domain,
            pages_crawled=len(pages),
            total_errors=len(errors),
            duration_ms=job.duration_ms or 0,
            started_at=job.started_at.isoformat() if job and job.started_at else None,
            completed_at=job.completed_at.isoformat() if job and job.completed_at else None,
            pages=page_list,
            errors=error_list,
            crawl_config=job.crawl_config or {} if job else crawl_config,
        )

    except ValueError as e:
        logger.warning(f"Invalid URL for test crawl: {body.url} - {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid URL: {str(e)}"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in test-crawler for URL: {body.url}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred: {str(e)}"
        )
