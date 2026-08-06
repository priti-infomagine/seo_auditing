"""
Scorer API Endpoint.
"""
from typing import Optional
from fastapi import APIRouter, HTTPException, status

from app.modules.scorer.schemas.scorer_schemas import ScoreRequest, SeoScoreResponse, RuleStatisticsResponse
from app.modules.scorer.services.scorer_service import ScorerService
from app.modules.crawler.crawl_service import CrawlerService
from app.modules.parser.services.parser_service import ParserService
from app.core.logger import logger


router = APIRouter()


@router.post("/score", response_model=SeoScoreResponse, tags=["Scorer"])
async def score_parsed_data(request: ScoreRequest):
    """
    Score parsed SEO data and return comprehensive SEO analysis.
    
    Accepts either:
    - parsed_data: Direct parsed data from parser service
    - url: URL to crawl, parse, and score
    - domain + test_number: Load existing crawl data and score it
    """
    scorer_service = ScorerService()
    
    # Option 1: Score provided parsed data directly
    if request.parsed_data:
        logger.info("Scoring provided parsed data")
        return await scorer_service.score_parsed_data(request.parsed_data)
    
    # Option 2: Crawl URL, parse, and score
    if request.url:
        logger.info(f"Scoring URL: {request.url}")
        
        # Crawl the URL
        crawl_service = CrawlerService()
        try:
            crawl_result = await crawl_service.crawl_url(request.url)
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e)
            )
        except RuntimeError as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Crawl failed: {str(e)}"
            )
        
        # Parse the HTML
        html = crawl_result.get("data", {}).get("html", "")
        if not html:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="No HTML content found in crawl result"
            )
        
        parser_service = ParserService()
        parsed_data = parser_service.parse_html(
            html=html,
            url=request.url,
            crawler_data=crawl_result.get("data", {})
        )
        
        # Score the parsed data
        return await scorer_service.score_parsed_data(parsed_data)
    
    # Option 3: Load existing crawl data by domain
    if request.domain:
        logger.info(f"Scoring domain: {request.domain}")
        
        # This would integrate with your storage service
        # For now, we'll use a simple file-based approach
        import json
        from pathlib import Path
        
        storage_dir = Path("app/storage/crawler") / request.domain
        if not storage_dir.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No crawl data found for domain: {request.domain}"
            )
        
        # Find the test file
        if request.test_number:
            pattern = f"*_test_{request.test_number}.json"
            files = sorted(storage_dir.glob(pattern))
        else:
            files = sorted(storage_dir.glob("*.json"), reverse=True)
        
        if not files:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No crawl data found for domain: {request.domain}"
            )
        
        # Load crawl data
        with open(files[0], 'r', encoding='utf-8') as f:
            crawl_data = json.load(f)
        
        # Parse and score
        html = crawl_data.get('html', '')
        url = crawl_data.get('url', '')
        
        parser_service = ParserService()
        parsed_data = parser_service.parse_html(html, url, crawl_data)
        
        return await scorer_service.score_parsed_data(parsed_data)
    
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Must provide either 'url', 'parsed_data', or 'domain'"
    )


@router.get("/rules/statistics", response_model=RuleStatisticsResponse, tags=["Scorer"])
async def get_rule_statistics():
    """
    Get statistics about loaded scoring rules.
    """
    scorer_service = ScorerService()
    stats = scorer_service.get_rule_statistics()
    
    return RuleStatisticsResponse(
        total_rules=stats["total_rules"],
        categories=stats["categories"]
    )


@router.get("/rules/categories", tags=["Scorer"])
async def get_rule_categories():
    """
    Get all available rule categories and their weights.
    """
    scorer_service = ScorerService()
    calculator = scorer_service.score_calculator
    
    return {
        "categories": list(calculator.weights.keys()),
        "weights": calculator.weights,
        "total_rules": len(scorer_service.rules),
    }