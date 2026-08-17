"""
POST /audit/analyze — Complete crawl → parse → score SEO audit pipeline.

Takes a URL as input, performs the full pipeline:
1. Crawls the URL
2. Parses the HTML content
3. Scores the parsed data using SEO rules

Returns comprehensive scored output after all rule checks.
"""
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
from app.modules.parser.services.parser_service import ParserService
from app.modules.scorer.services.scorer_service import ScorerService

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
        import json
        from pathlib import Path
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
        
        return AuditAnalyzeResponse(
            success=True,
            message="SEO audit completed successfully",
            url=crawl_result["url"],
            domain=crawl_result["domain"],
            crawl=crawl_summary,
            seo_score=seo_score_report,
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