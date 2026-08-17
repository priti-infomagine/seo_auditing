"""
POST /audit/analyze — Complete crawl → parse → score SEO audit pipeline.

Takes a URL as input, performs the full pipeline:
1. Crawls the URL
2. Parses the HTML content
3. Scores the parsed data using SEO rules

Returns comprehensive scored output after all rule checks.
"""
import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.logger import logger
from app.modules.audit.schemas.audit_schemas import (
    AuditAnalyzeRequest,
    AuditAnalyzeResponse,
    CrawlSummarySchema,
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
from app.modules.parser.services.parser_service import ParserService
from app.modules.scorer.services.scorer_service import ScorerService
from app.modules.audit.services.analysis_scorer_service import AnalysisScorerService
from app.modules.audit.services.db_parser_service import DBParserService
from app.modules.audit.services.rule_evaluator_service import RuleEvaluatorService

router = APIRouter()


@router.post(
    "/analyze",
    response_model=AuditAnalyzeResponse,
    status_code=200,
    summary="Run complete SEO audit pipeline",
    description="Crawls the provided URL, parses HTML content, and runs comprehensive SEO scoring rules to return final scored output",
)
async def analyze_website(
    body: AuditAnalyzeRequest,
    db: AsyncSession = Depends(get_db),
) -> AuditAnalyzeResponse:
    """
    Run complete crawl → parse → score SEO audit pipeline.
    
    Args:
        body: AuditAnalyzeRequest containing URL to analyze
        db: Database session (required by architecture, though not used)
        
    Returns:
        AuditAnalyzeResponse with crawl results, parsed data, and comprehensive SEO scores
        
    Raises:
        HTTPException: If crawl, parse, or scoring fails
    """
    logger.info(f"POST /audit/analyze - Full audit pipeline started for URL: {body.url}")
    
    try:
        # Step 1: Crawl the URL
        logger.info("Step 1: Starting crawl phase")
        crawler_service = CrawlerService()
        crawl_result = await crawler_service.crawl_url(body.url)
        
        # Extract crawl summary info
        crawl_summary = CrawlSummarySchema(
            url=crawl_result["url"],
            domain=crawl_result["domain"],
            status_code=crawl_result["data"].get("status_code", 0),
            response_time=crawl_result["data"].get("response_time", 0.0),
            html_size_bytes=crawl_result["data"].get("html_size", 0),
            test_number=crawl_result["test_number"],
            file_path=crawl_result["file_path"],
            crawled_at=crawl_result["crawled_at"],
        )
        
        # Load the full crawl data from the saved file to get HTML
        filepath = Path(crawl_result["file_path"])
        with open(filepath, 'r', encoding='utf-8') as f:
            full_crawl_data = json.load(f)
        
        html = full_crawl_data.get("html", "")
        if not html:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="No HTML content found in crawl result"
            )
        
        # Merge full crawl data for parser
        crawler_data_for_parser = {
            "html": html,
            "http": full_crawl_data.get("http", {}),
            "ssl": full_crawl_data.get("ssl", {}),
            "security_headers": full_crawl_data.get("security_headers", {}),
            "performance": full_crawl_data.get("performance", {}),
            "resources": full_crawl_data.get("resources", {}),
            "javascript": full_crawl_data.get("javascript", {}),
            "robots": full_crawl_data.get("robots", {}),
            "sitemap": full_crawl_data.get("sitemap", {}),
        }
        
        # Step 2: Parse the HTML
        logger.info("Step 2: Starting parse phase")
        parser_service = ParserService()
        parsed_data = parser_service.parse_html(
            html=html,
            url=body.url,
            crawler_data=crawler_data_for_parser
        )
        
        if not parsed_data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Parsing produced no data"
            )
        
        # Step 3: Score the parsed data
        logger.info("Step 3: Starting scoring phase")
        scorer_service = ScorerService()
        seo_score_report = await scorer_service.score_parsed_data(parsed_data)
        
        logger.info(
            f"Audit pipeline completed successfully for URL: {body.url} "
            f"- SEO Score: {seo_score_report['overall_score']}/100 "
            f"(Grade: {seo_score_report['grade']})"
        )
        
        # Step 4: Persist crawl data to DB (DB-backed pipeline, no Celery/tasks)
        logger.info("Step 4: Starting DB persistence phase")
        project_id = uuid.uuid4()
        test_user_id = uuid.UUID("00000000-0000-0000-0000-000000000000")
        
        # 4a: Create CrawlJob in DB
        domain = crawl_result["domain"]
        crawl_config_dict = {
            "max_pages": 1,
            "max_depth": 0,
            "concurrency": 1,
        }
        db_crawl_job = CrawlJob(
            project_id=project_id,
            user_id=test_user_id,
            url=body.url,
            domain=domain,
            status="crawling",
            max_pages=1,
            max_depth=0,
            crawl_config=crawl_config_dict,
            pages_discovered=1,
            pages_crawled=1,
        )
        db_crawl_job = await CrawlJobRepository(db).create(db_crawl_job)
        crawl_id = db_crawl_job.id
        
        # 4b: Create CrawlPage in DB
        parsed_url = urlparse(crawl_result["url"])
        page = CrawlPage(
            crawl_id=crawl_id,
            url=crawl_result["url"],
            normalized_url=crawl_result["url"],
            url_hash=hashlib.md5(crawl_result["url"].encode()).hexdigest(),
            scheme=parsed_url.scheme,
            host=parsed_url.netloc,
            path=parsed_url.path,
            query=parsed_url.query,
            final_url=crawl_result["url"],
            status_code=crawl_result["data"].get("http", {}).get("status_code", 0),
            content_type=crawl_result["data"].get("http", {}).get("content_type", ""),
            content_length=len(html),
            response_time_ms=int(
                crawl_result["data"].get("http", {}).get("response_time_ms", 0)
            ),
            depth=0,
            is_crawled=True,
            is_success=True,
            is_redirect=False,
            is_error=False,
        )
        page = await CrawlPageRepository(db).create(page)
        
        # 4c: Persist HTML snapshot
        await PageSnapshotRepository(db).save_snapshot(
            page_id=page.id,
            html_content=html,
        )
        
        # 4d: Persist SEO data
        meta = parsed_data.get("metadata", {}) or {}
        content_data = parsed_data.get("content", {}) or {}
        await PageSEODataRepository(db).upsert(PageSEOData(
            page_id=page.id,
            title=meta.get("title", ""),
            title_length=meta.get("title_length", 0),
            meta_description=meta.get("meta_description", ""),
            meta_description_length=meta.get("meta_description_length", 0),
            canonical=meta.get("canonical", ""),
            robots_meta=meta.get("robots_meta", ""),
            language=meta.get("language", "") or meta.get("page_language", ""),
            charset=meta.get("charset", ""),
            viewport=meta.get("viewport", ""),
            favicon=meta.get("favicon", ""),
            word_count=content_data.get("word_count", 0),
            content_hash=content_data.get("content_hash", ""),
            content=content_data,
            structured_data={"exists": len(parsed_data.get("schemas", [])) > 0},
            social=parsed_data.get("social", {}) or {},
            accessibility={},
            page_metadata={},
        ))
        
        # 4e: Persist network data
        http_data = full_crawl_data.get("http", {})
        await PageNetworkDataRepository(db).upsert(PageNetworkData(
            page_id=page.id,
            status_code=http_data.get("status_code", 0),
            content_type=http_data.get("content_type", ""),
            content_length=http_data.get("content_size", 0),
            response_time_ms=http_data.get("response_time_ms", 0),
            headers=http_data.get("headers", {}),
            redirects=http_data.get("redirect_chain", []),
            security=full_crawl_data.get("ssl", {}),
            performance=full_crawl_data.get("technical", {}) or {},
        ))
        
        # 4f: Update CrawlJob status to completed
        db_crawl_job.status = "completed"
        db_crawl_job.completed_at = datetime.now(timezone.utc)
        await CrawlJobRepository(db).update(db_crawl_job)
        
        logger.info(f"DB persistence completed: crawl_id={crawl_id}, page_id={page.id}")
        
        # Step 5: DB-backed parse (reads snapshot from DB, saves ParsedPageFact)
        logger.info("Step 5: Starting DB-backed parse phase")
        db_parser = DBParserService(db)
        parse_result = await db_parser.parse_crawl(project_id, crawl_id, force=True)
        logger.info(
            f"DB parse: {parse_result['pages_parsed']} pages parsed, "
            f"{parse_result['pages_failed']} failed"
        )
        
        # Step 6: DB-backed rule evaluation
        logger.info("Step 6: Starting DB-backed rule evaluation")
        evaluator = RuleEvaluatorService(db)
        eval_result = await evaluator.evaluate_crawl(project_id, crawl_id, force=True)
        logger.info(
            f"DB evaluate: {eval_result['rules_run']} rules run, "
            f"{eval_result['total_results']} results, {len(eval_result['errors'])} errors"
        )
        
        # Step 7: DB-backed scoring
        logger.info("Step 7: Starting DB-backed scoring")
        db_scorer = AnalysisScorerService(db)
        db_score_report = await db_scorer.score_project(project_id, crawl_id, force=True)
        logger.info(
            f"DB scoring completed: Score={db_score_report['overall_score']}/100 "
            f"(Grade: {db_score_report['grade']})"
        )
        
        return AuditAnalyzeResponse(
            success=True,
            message="SEO audit completed successfully",
            url=crawl_result["url"],
            domain=crawl_result["domain"],
            crawl=crawl_summary,
            seo_score=db_score_report,
            parsed_data=parsed_data,
        )
        
    except ValueError as e:
        # Invalid URL or validation error
        logger.warning(f"Invalid URL provided: {body.url} - {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid URL: {str(e)}"
        )
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except RuntimeError as e:
        # Crawl or parse failed
        logger.error(f"Audit pipeline failed for URL: {body.url} - {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Audit failed: {str(e)}"
        )
    except Exception as e:
        # Unexpected error
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