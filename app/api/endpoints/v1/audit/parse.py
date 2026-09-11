"""
POST /audit/parse/{audit_id} — Trigger DB-backed parsing for a completed crawl.

Reads crawl pages + HTML snapshots from PostgreSQL, runs the parser, and persists parsed_page_facts.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.core.database import get_db
from app.core.logger import logger
from app.modules.audit.schemas.analysis_schemas import (
    ParseTriggerRequest,
)
from app.modules.audit.services.db_parser_service import DBParserService
from app.modules.crawler.repositories.crawl_job_repository import CrawlJobRepository

router = APIRouter()


@router.post(
    "/parse/{audit_id}",
    summary="Parse crawled pages and persist page facts to DB",
    description=(
        "Reads HTML snapshots from PostgreSQL for a completed crawl job, "
        "runs the parser on each page, and persists ParsedPageFact rows."
    ),
)
async def parse_crawl(
    audit_id: UUID,
    body: ParseTriggerRequest = None,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Trigger DB-backed parsing for a completed crawl.

    Args:
        audit_id: The audit ID (== crawl_id).
        body: Optional request with force flag.
        db: Database session.

    Returns:
        Dict with audit_id, parse summary.

    Raises:
        HTTPException 404: CrawlJob not found.
        HTTPException 409: CrawlJob still in progress.
    """
    logger.info(f"POST /audit/parse/{audit_id}")

    try:
        job_repo = CrawlJobRepository(db)
        job = await job_repo.get_by_id(audit_id)
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Crawl job {audit_id} not found",
            )

        if job.status != "completed":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Crawl job is not completed (status={job.status}). "
                       f"Wait for crawl to finish before parsing.",
            )

        force = body.force if body else False

        parser_service = DBParserService(db)
        result = await parser_service.parse_crawl(audit_id, force=force)

        logger.info(
            f"POST /audit/parse/{audit_id} - "
            f"parsed={result['pages_parsed']}, failed={result['pages_failed']}"
        )

        return {
            "audit_id": str(audit_id),
            "crawl_id": str(audit_id),
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
            f"POST /audit/parse/{audit_id}: unexpected error - {exc}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred during parsing",
        )
