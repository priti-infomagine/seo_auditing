"""
POST /audit/score/{audit_id} — Score SEO analysis for a crawl.

Reads rule evaluation results from PostgreSQL, computes weighted SEO scores per
page and aggregate scores, persists to seo_analysis_runs, and writes the output
JSON file to app/output/{domain}_{audit_id}.json.

Returns the unified audit response shape.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.core.database import get_db
from app.core.logger import logger
from app.modules.audit.schemas.analysis_schemas import (
    ScoreTriggerRequest,
    SeoAnalysisResponse,
)
from app.modules.audit.services.analysis_scorer_service import AnalysisScorerService
from app.modules.audit.services.audit_response_builder import AuditResponseBuilder
from app.modules.crawler.repositories.crawl_job_repository import CrawlJobRepository
from app.modules.audit.repositories.seo_analysis_repository import SeoAnalysisRunRepository
from app.modules.audit.repositories.rule_evaluation_repository import RuleEvaluationResultRepository

router = APIRouter()


@router.post(
    "/score/{audit_id}",
    summary="Score SEO analysis and persist results",
    description=(
        "Reads rule evaluation results from PostgreSQL, computes weighted "
        "SEO scores per page and aggregate scores, persists to "
        "seo_analysis_runs table, and writes the output JSON file."
    ),
)
async def score_project(
    audit_id: UUID,
    body: ScoreTriggerRequest = None,
    db: AsyncSession = Depends(get_db),
) -> SeoAnalysisResponse:
    """
    Trigger full scoring for a crawl with completed evaluation.

    Args:
        audit_id: The audit ID (== crawl_id).
        body: Request with force flag.
        db: Database session.

    Returns:
        UnifiedAuditResponse with full score breakdown.

    Raises:
        HTTPException 404: No rule results or crawl job.
    """
    logger.info(f"POST /audit/score/{audit_id}")

    try:
        job_repo = CrawlJobRepository(db)
        job = await job_repo.get_by_id(audit_id)
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Crawl job {audit_id} not found",
            )

        force = body.force if body else False
        analysis_repo = SeoAnalysisRunRepository(db)
        builder = AuditResponseBuilder(db)

        existing = await analysis_repo.get_by_audit_id(audit_id)
        if existing and existing.analysis_status == "completed" and not force:
            logger.info(f"POST /audit/score/{audit_id}: returning cached result")
            return await builder.build(audit_id)

        rule_eval_repo = RuleEvaluationResultRepository(db)
        eval_results = await rule_eval_repo.get_by_audit_id(audit_id)

        if not eval_results:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No rule evaluation results found for audit_id={audit_id}. "
                       f"Run POST /audit/evaluate/{audit_id} first.",
            )

        scorer = AnalysisScorerService(db)
        unified = await scorer.score_project(audit_id, force=force)

        logger.info(
            f"POST /audit/score/{audit_id} - "
            f"score={unified['summary']['score']}"
        )

        return unified

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            f"POST /audit/score/{audit_id}: unexpected error - {exc}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred during scoring",
        )
