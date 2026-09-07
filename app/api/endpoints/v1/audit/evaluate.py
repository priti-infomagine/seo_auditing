"""
POST /audit/evaluate/{crawl_id} — Trigger rule evaluation for a crawl.

Reads parsed page facts from PostgreSQL, reconstructs the data dict that
SEO rules expect, runs all 60+ rules, and persists results to
`rule_evaluation_results`.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID, uuid4

from app.core.database import get_db
from app.core.logger import logger
from app.modules.audit.schemas.analysis_schemas import (
    EvaluateTriggerRequest,
)
from app.modules.audit.services.rule_evaluator_service import RuleEvaluatorService
from app.modules.crawler.repositories.crawl_job_repository import CrawlJobRepository
from app.modules.audit.repositories.parsed_page_fact_repository import ParsedPageFactRepository

router = APIRouter()


@router.post(
    "/evaluate/{crawl_id}",
    summary="Evaluate SEO rules for all parsed pages in a crawl",
    description=(
        "Reads parsed page facts from PostgreSQL, reconstructs the rule data dict "
        "from DB rows, runs all 60+ SEO rules per page, and persists results "
        "to rule_evaluation_results. Uses project_id as tracking key."
    ),
)
async def evaluate_crawl(
    crawl_id: UUID,
    body: EvaluateTriggerRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Trigger rule evaluation for all parsed pages of a crawl.

    Args:
        crawl_id: The crawl job ID.
        body: Request with project_id (links to parse phase) and force flag.
        db: Database session.

    Returns:
        Dict with project_id, crawl_id, evaluation summary.

    Raises:
        HTTPException 404: CrawlJob not found or no parsed facts.
        HTTPException 403: Access denied.
    """
    user_id = uuid4()
    logger.info(
        f"POST /audit/evaluate/{crawl_id} - "
        f"project_id={body.project_id}, user_id={user_id}"
    )

    try:
        job_repo = CrawlJobRepository(db)
        job = await job_repo.get_by_id(crawl_id)
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Crawl job {crawl_id} not found",
            )

        parsed_fact_repo = ParsedPageFactRepository(db)
        parsed_facts = await parsed_fact_repo.get_by_crawl_id(crawl_id)
        project_facts = [f for f in parsed_facts if str(f.project_id) == str(body.project_id)]

        if not project_facts and not body.force:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No parsed facts found for project_id={body.project_id}. "
                       f"Run POST /audit/parse/{crawl_id} first.",
            )

        # Run evaluator (inline for now, can be Celery for large crawls)
        evaluator = RuleEvaluatorService(db)
        result = await evaluator.evaluate_crawl(
            body.project_id, crawl_id, force=body.force
        )

        logger.info(
            f"POST /audit/evaluate/{crawl_id} - "
            f"pages_evaluated={result['pages_evaluated']}, "
            f"total_results={result['total_results']}"
        )

        return {
            "project_id": result["project_id"],
            "crawl_id": result["crawl_id"],
            "status": "completed",
            "message": f"Evaluation completed: {result['pages_evaluated']} pages evaluated, "
                       f"{result['total_results']} total rule results, "
                       f"{len(result['errors'])} errors",
            "pages_evaluated": result["pages_evaluated"],
            "rules_run": result["rules_run"],
            "total_results": result["total_results"],
            "errors": result["errors"],
            "evaluated_at": result["evaluated_at"],
        }

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            f"POST /audit/evaluate/{crawl_id}: unexpected error - {exc}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred during rule evaluation",
        )
