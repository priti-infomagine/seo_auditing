"""
POST /audit/parse/{crawl_id} — Trigger DB-backed parsing for a completed crawl.

Creates a project_id if not provided, reads crawl pages + HTML snapshots
from PostgreSQL, runs the parser, and persists parsed_page_facts.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID, uuid4

from app.core.database import get_db
from app.core.logger import logger
from app.core.security import get_current_user
from app.modules.audit.schemas.analysis_schemas import (
    ParseTriggerRequest,
    AnalysisError,
)
from app.modules.audit.services.db_parser_service import DBParserService
from app.modules.crawler.repositories.crawl_job_repository import CrawlJobRepository
from app.modules.auth.models.users import User

router = APIRouter()


@router.post(
    "/parse/{crawl_id}",
    summary="Parse crawled pages and persist page facts to DB",
    description=(
        "Reads HTML snapshots from PostgreSQL for a completed crawl job, "
        "runs the parser on each page, and persists ParsedPageFact rows. "
        "Uses project_id as the tracking key. Returns immediately with "
        "parse results (inline for small crawls, async Celery for large)."
    ),
)
async def parse_crawl(
    crawl_id: UUID,
    body: ParseTriggerRequest = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    Trigger DB-backed parsing for a completed crawl.

    Args:
        crawl_id: The crawl job ID (from POST /crawler/crawl).
        body: Optional request with project_id and force flag.
        db: Database session.
        current_user: Authenticated user.

    Returns:
        Dict with project_id, crawl_id, parse summary.

    Raises:
        HTTPException 404: CrawlJob not found or doesn't belong to user.
        HTTPException 409: CrawlJob still in progress.
    """
    logger.info(f"POST /audit/parse/{crawl_id} - user_id={current_user.id}")

    try:
        # Load crawl job
        job_repo = CrawlJobRepository(db)
        job = await job_repo.get_by_id(crawl_id)
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Crawl job {crawl_id} not found",
            )

        # Verify ownership
        if str(job.user_id) != str(current_user.id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this crawl job",
            )

        # Check crawl status
        if job.status != "completed":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Crawl job is not completed (status={job.status}). "
                       f"Wait for crawl to finish before parsing.",
            )

        # Determine project_id
        if body and body.project_id:
            project_id = body.project_id
        else:
            project_id = job.project_id or uuid4()

        force = body.force if body else False

        # Run parser service (inline — fast, CPU-bound, uses DB)
        parser_service = DBParserService(db)
        result = await parser_service.parse_crawl(project_id, crawl_id, force=force)

        logger.info(
            f"POST /audit/parse/{crawl_id} - "
            f"parsed={result['pages_parsed']}, failed={result['pages_failed']}"
        )

        return {
            "project_id": result["project_id"],
            "crawl_id": result["crawl_id"],
            "status": "completed",
            "message": f"Parsing completed: {result['pages_parsed']} pages parsed, "
                       f"{result['pages_failed']} failed, {result['pages_skipped']} skipped",
            "pages_parsed": result["pages_parsed"],
            "pages_failed": result["pages_failed"],
            "pages_skipped": result["pages_skipped"],
            "errors": result["errors"],
            "parsed_at": result["parsed_at"],
        }

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            f"POST /audit/parse/{crawl_id}: unexpected error - {exc}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred during parsing",
        )
