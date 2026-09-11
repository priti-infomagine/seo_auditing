"""
POST /audit/evaluate/{audit_id} — Trigger rule evaluation for a crawl.

Reads parsed page facts from PostgreSQL, reconstructs the data dict that
SEO rules expect, runs all 60+ rules, and persists results to
`rule_evaluation_results`.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

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
    "/evaluate/{audit_id}",
    summary="Evaluate SEO rules for all parsed pages in a crawl",
    description=(
        "Reads parsed page facts from PostgreSQL, reconstructs the rule data dict "
        "from DB rows, runs all 60+ SEO rules per page, and persists results "
        "to rule_evaluation_results."
    ),
)
async def evaluate_crawl(
    audit_id: UUID,
    body: EvaluateTriggerRequest = None,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Trigger rule evaluation for all parsed pages of a crawl.

    Args:
        audit_id: The audit ID (== crawl_id).
        body: Request with force flag.
        db: Database session.

    Returns:
        Dict with audit_id, evaluation summary.

    Raises:
        HTTPException 404: CrawlJob not found or no parsed facts.
    """
    logger.info(f"POST /audit/evaluate/{audit_id}")

    try:
        job_repo = CrawlJobRepository(db)
        job = await job_repo.get_by_id(audit_id)
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Crawl job {audit_id} not found",
            )

        parsed_fact_repo = ParsedPageFactRepository(db)
        parsed_facts = await parsed_fact_repo.get_by_audit_id(audit_id)

        force = body.force if body else False
        if not parsed_facts and not force:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No parsed facts found for audit_id={audit_id}. "
                       f"Run POST /audit/parse/{audit_id} first.",
            )

        evaluator = RuleEvaluatorService(db)
        result = await evaluator.evaluate_crawl(audit_id, force=force)

        logger.info(
            f"POST /audit/evaluate/{audit_id} - "
            f"pages_evaluated={result['pages_evaluated']}, "
            f"total_results={result['total_results']}"
        )

        return {
            "audit_id": str(audit_id),
            "crawl_id": str(audit_id),
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
            f"POST /audit/evaluate/{audit_id}: unexpected error - {exc}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred during rule evaluation",
        )
