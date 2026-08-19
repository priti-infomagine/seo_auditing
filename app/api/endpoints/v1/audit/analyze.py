"""
POST /audit/analyze — Complete crawl → parse → score SEO audit pipeline.

Takes a URL as input, performs the full pipeline:
1. Crawls multiple pages (sitemap-first, BFS-fallback)
2. Persists crawl data to DB (CrawlPage, snapshot, SEO data, network data)
3. DB-backed parse → rule evaluation → scoring
4. Returns per-page breakdown with scores, rule results, and links analysis
"""
import hashlib
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.logger import logger
from app.modules.audit.schemas.audit_schemas import (
    AuditAnalyzeRequest,
    AuditAnalyzeResponse,
)
from app.modules.crawler.crawl_service import CrawlerService
from app.modules.crawler.models.crawl_jobs import CrawlJob
from app.modules.crawler.models.crawl_pages import CrawlPage
from app.modules.crawler.models.page_network_data import PageNetworkData
from app.modules.crawler.models.page_seo_data import PageSEOData
from app.modules.crawler.models.page_snapshots import PageSnapshot
from app.modules.crawler.repositories.crawl_job_repository import CrawlJobRepository
from app.modules.crawler.repositories.crawl_page_repository import CrawlPageRepository
from app.modules.crawler.repositories.page_network_data_repository import (
    PageNetworkDataRepository,
)
from app.modules.crawler.repositories.page_seo_data_repository import (
    PageSEODataRepository,
)
from app.modules.crawler.repositories.page_snapshot_repository import (
    PageSnapshotRepository,
)
from app.modules.parser.services.parser_orchestrator import ParserOrchestrator
from app.modules.audit.services.analysis_scorer_service import AnalysisScorerService
from app.modules.audit.services.db_parser_service import DBParserService
from app.modules.audit.services.rule_evaluator_service import RuleEvaluatorService

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
        # Step 1: Multi-page crawl
        logger.info("Step 1: Starting crawl phase (multi-page)")
        crawler_service = CrawlerService()
        crawl_results = await crawler_service.crawl_site(
            body.url,
            max_pages=body.max_pages,
            max_depth=body.max_depth,
        )

        if not crawl_results:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Crawl produced no results"
            )

        logger.info(f"Crawl phase completed: {len(crawl_results)} pages crawled")

        # Use first result for project/domain setup
        first_result = crawl_results[0]

        # Step 2: Create CrawlJob and persist each crawled page
        logger.info("Step 2: Starting DB persistence phase")
        project_id = uuid.uuid4()
        test_user_id = uuid.UUID("00000000-0000-0000-0000-000000000000")

        # 2a: Create CrawlJob in DB
        domain = first_result["domain"]
        crawl_config_dict = {
            "max_pages": body.max_pages,
            "max_depth": body.max_depth,
            "concurrency": 1,
        }
        db_crawl_job = CrawlJob(
            project_id=project_id,
            user_id=test_user_id,
            url=body.url,
            domain=domain,
            status="crawling",
            max_pages=body.max_pages,
            max_depth=body.max_depth,
            crawl_config=crawl_config_dict,
            pages_discovered=len(crawl_results),
            pages_crawled=len(crawl_results),
        )
        db_crawl_job = await CrawlJobRepository(db).create(db_crawl_job)
        crawl_id = db_crawl_job.id

        # 2b-2e: Create CrawlPage + persist snapshot/SEO/network data for each page
        parser = ParserOrchestrator()
        crawl_page_repo = CrawlPageRepository(db)
        snapshot_repo = PageSnapshotRepository(db)
        seo_repo = PageSEODataRepository(db)
        network_repo = PageNetworkDataRepository(db)

        for idx, crawl_result in enumerate(crawl_results):
            html = crawl_result["data"].get("html", "")
            if not html:
                logger.warning(f"Page {idx} ({crawl_result['url']}): no HTML, skipping persistence")
                continue

            # Parse HTML to extract SEO-relevant metadata
            parsed = parser.parse(html=html, url=crawl_result["url"])
            parsed_dict = parsed.model_dump(mode="json") if hasattr(parsed, "model_dump") else {}
            metadata = parsed_dict.get("metadata", {}) or {}
            content_data = parsed_dict.get("content", {}) or {}

            # 2b: Create CrawlPage in DB
            page_url = crawl_result["url"]
            parsed_url = urlparse(page_url)
            page = CrawlPage(
                crawl_id=crawl_id,
                url=page_url,
                normalized_url=page_url,
                url_hash=hashlib.md5(page_url.encode()).hexdigest(),
                scheme=parsed_url.scheme,
                host=parsed_url.netloc,
                path=parsed_url.path,
                query=parsed_url.query,
                final_url=page_url,
                status_code=crawl_result["data"].get("http", {}).get("status_code", 0),
                content_type=crawl_result["data"].get("http", {}).get("content_type", ""),
                content_length=len(html),
                response_time_ms=int(
                    crawl_result["data"].get("http", {}).get("response_time_ms", 0)
                ),
                depth=idx,  # 0 = start page, 1+ = discovered via links
                is_crawled=True,
                is_success=crawl_result["data"].get("http", {}).get("status_code", 0) == 200,
                is_redirect=False,
                is_error=crawl_result["data"].get("http", {}).get("status_code", 0) >= 400,
            )
            page = await crawl_page_repo.create(page)

            # 2c: Persist HTML snapshot
            await snapshot_repo.save_snapshot(page_id=page.id, html_content=html)

            # 2d: Persist SEO data
            await seo_repo.upsert(PageSEOData(
                page_id=page.id,
                title=metadata.get("title", ""),
                title_length=metadata.get("title_length", 0),
                meta_description=metadata.get("meta_description", ""),
                meta_description_length=metadata.get("meta_description_length", 0),
                canonical=metadata.get("canonical", ""),
                robots_meta=metadata.get("robots_meta", ""),
                language=metadata.get("language", "") or metadata.get("page_language", ""),
                charset=metadata.get("charset", ""),
                viewport=metadata.get("viewport", ""),
                favicon=metadata.get("favicon", ""),
                word_count=content_data.get("word_count", 0),
                content_hash=content_data.get("content_hash", ""),
                content=content_data,
                structured_data={
                    "schemas": parsed_dict.get("schemas", []),
                    "exists": len(parsed_dict.get("schemas", [])) > 0,
                },
                social=parsed_dict.get("social", {}) or {},
                accessibility={},
                page_metadata={},
            ))

            # 2e: Persist network data
            http_data = crawl_result["data"].get("http", {})
            await network_repo.upsert(PageNetworkData(
                page_id=page.id,
                status_code=http_data.get("status_code", 0),
                content_type=http_data.get("content_type", ""),
                content_length=http_data.get("content_size", 0),
                response_time_ms=http_data.get("response_time_ms", 0),
                headers=http_data.get("headers", {}),
                redirects=http_data.get("redirect_chain", []),
                security={},
                performance={},
            ))

        # 2f: Update CrawlJob status to completed
        db_crawl_job.status = "completed"
        db_crawl_job.completed_at = datetime.now(timezone.utc)
        await CrawlJobRepository(db).update(db_crawl_job)

        logger.info(f"DB persistence completed: crawl_id={crawl_id}")

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
