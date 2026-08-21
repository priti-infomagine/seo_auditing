"""
POST /audit/analyze — Complete crawl → parse → score SEO audit pipeline.

Takes a URL as input, performs the full pipeline:
1. Crawls multiple pages (sitemap-first, BFS-fallback)
2. Persists crawl data to DB (CrawlPage, snapshot, SEO data, network data)
3. DB-backed parse → rule evaluation → scoring
4. Returns per-page breakdown with scores, rule results, and links analysis
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.logger import logger
from app.core.config import settings
from app.modules.audit.schemas.audit_schemas import (
    AuditAnalyzeRequest,
    AuditAnalyzeResponse,
)
from app.modules.audit.services.analysis_scorer_service import AnalysisScorerService
from app.modules.audit.services.db_parser_service import DBParserService
from app.modules.audit.services.rule_evaluator_service import RuleEvaluatorService
from app.modules.crawler.models.crawl_jobs import CrawlJob
from app.modules.crawler.repositories.crawl_job_repository import CrawlJobRepository
from app.modules.crawler.services.crawl_orchestrator import CrawlOrchestrator
from app.shared.utils.url_utils import get_domain

router = APIRouter()


@router.post(
    "/analyze",
    response_model=AuditAnalyzeResponse,
    status_code=200,
    summary="Run complete SEO audit pipeline",
    description="Crawls multiple pages from the provided URL, parses HTML content, and runs comprehensive SEO scoring rules to return final scored output with per-page breakdown",
)
async def analyze_website(
    body: AuditAnalyzeRequest,
    db: AsyncSession = Depends(get_db),
) -> AuditAnalyzeResponse:
    """
    Run complete crawl → parse → score SEO audit pipeline.

    Args:
        body: AuditAnalyzeRequest containing URL to analyze and crawl limits
        db: Database session

    Returns:
        AuditAnalyzeResponse with crawl summary, SEO scores, and per-page breakdown

    Raises:
        HTTPException: If crawl, parse, or scoring fails
    """
    logger.info(f"POST /audit/analyze - Full audit pipeline started for URL: {body.url}")

    try:
        # Step 1: Create CrawlJob (queued) before crawling starts
        logger.info("Step 1: Creating CrawlJob")
        project_id = uuid.uuid4()
        test_user_id = uuid.UUID("00000000-0000-0000-0000-000000000000")
        domain = get_domain(body.url)
        if not domain:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid URL: {body.url} - could not extract domain",
            )

        effective_max_pages = min(body.max_pages, settings.CRAWL_MAX_PAGES) if body.max_pages is not None else settings.CRAWL_MAX_PAGES

        crawl_config_dict = {
            "max_pages": effective_max_pages,
            "max_depth": body.max_depth if body.max_depth is not None else 5,
            "concurrency": body.concurrency,
            "request_timeout": 30,
            "delay_ms": 0,
            "follow_redirects": True,
            "respect_robots": True,
        }
        db_crawl_job = CrawlJob(
            project_id=project_id,
            user_id=test_user_id,
            url=body.url,
            domain=domain,
            status="queued",
            max_pages=effective_max_pages,
            max_depth=body.max_depth if body.max_depth is not None else 5,
            crawl_config=crawl_config_dict,
        )
        db_crawl_job = await CrawlJobRepository(db).create(db_crawl_job)
        crawl_id = db_crawl_job.id

        logger.info("Step 2: Running CrawlOrchestrator (multi-page, concurrent)")
        orchestrator = CrawlOrchestrator(db, crawl_id)
        orchestrator_result = await orchestrator.run(
            start_url=body.url,
            max_depth=body.max_depth if body.max_depth is not None else 5,
            max_pages=effective_max_pages,
            concurrency=body.concurrency,
        )

        if orchestrator_result.get("status") == "failed":
            logger.error(f"Crawl failed for {body.url}: {orchestrator_result}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Crawl failed — see logs for details",
            )

        pages_crawled = orchestrator_result.get("pages_crawled", 0)
        pages_discovered = orchestrator_result.get("pages_discovered", 0)

        if pages_crawled == 0:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Crawl produced no results",
            )

        logger.info(
            f"Crawl phase completed: {pages_crawled} pages crawled, "
            f"{pages_discovered} pages discovered"
        )

        # Step 3: DB-backed parse (reads snapshot from DB, saves ParsedPageFact)
        logger.info("Step 3: Starting DB-backed parse phase")
        db_parser = DBParserService(db)
        parse_result = await db_parser.parse_crawl(project_id, crawl_id, force=True)
        logger.info(
            f"DB parse: {parse_result['pages_parsed']} pages parsed, "
            f"{parse_result['pages_failed']} failed"
        )

        # Step 4: DB-backed rule evaluation
        logger.info("Step 4: Starting DB-backed rule evaluation")
        evaluator = RuleEvaluatorService(db)
        eval_result = await evaluator.evaluate_crawl(project_id, crawl_id, force=True)
        logger.info(
            f"DB evaluate: {eval_result['rules_run']} rules run, "
            f"{eval_result['total_results']} results, {len(eval_result['errors'])} errors"
        )

        # Step 5: DB-backed scoring (returns the unified audit response)
        logger.info("Step 5: Starting DB-backed scoring")
        db_scorer = AnalysisScorerService(db)
        unified = await db_scorer.score_project(project_id, crawl_id, force=True)
        logger.info(
            f"DB scoring completed: Score={unified['summary']['overall_score']}/100 "
            f"(Health: {unified['summary']['health']})"
        )

        return unified

    except ValueError as e:
        logger.warning(f"Invalid URL provided: {body.url} - {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid URL: {str(e)}"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error during audit for URL: {body.url}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred during SEO audit"
        )


@router.get("/health", tags=["Audit"])
async def audit_health_check():
    """Health check for audit endpoint."""
    try:
        return {
            "status": "healthy",
            "service": "audit-analyze",
            "endpoints": ["/api/v1/audit/analyze"],
        }
    except Exception as exc:
        logger.error(f"audit_health_check: unexpected error: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Audit service health check failed",
        )


