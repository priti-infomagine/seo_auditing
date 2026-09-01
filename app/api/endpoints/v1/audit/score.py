"""
POST /audit/score/{crawl_id} — Score SEO analysis for a crawl.

Reads rule evaluation results from PostgreSQL, computes weighted SEO scores per
page and aggregate project-level scores, persists to seo_analysis_runs, and
writes the output JSON file to app/output/{domain}_{project_id}.json.

Returns the unified audit response shape (audit, summary, categories, issues,
category_results, crawl, indexation, ...).
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID, uuid4

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
    "/score/{crawl_id}",
    summary="Score SEO analysis and persist results",
    description=(
        "Reads rule evaluation results from PostgreSQL, computes weighted "
        "SEO scores per page and aggregate project-level scores, persists to "
        "seo_analysis_runs table, and writes the output JSON file to "
        "app/output/{domain}_{project_id}.json."
    ),
)
async def score_project(
    crawl_id: UUID,
    body: ScoreTriggerRequest,
    db: AsyncSession = Depends(get_db),
) -> SeoAnalysisResponse:
    """
    Trigger full scoring for a crawl with completed evaluation.

    Args:
        crawl_id: The crawl job ID.
        body: Request with project_id and force flag.
        db: Database session.

    Returns:
        UnifiedAuditResponse with full score breakdown.

    Raises:
        HTTPException 404: No rule results or crawl job.
        HTTPException 409: Already scored and force=False.
    """
    user_id = uuid4()
    logger.info(
        f"POST /audit/score/{crawl_id} - "
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

        analysis_repo = SeoAnalysisRunRepository(db)
        builder = AuditResponseBuilder(db)

        existing = await analysis_repo.get_by_project_id(body.project_id)
        if existing and existing.analysis_status == "completed" and not body.force:
            logger.info(
                f"POST /audit/score/{crawl_id}: returning cached result for "
                f"project_id={body.project_id}"
            )
            return await builder.build(body.project_id, crawl_id)

        rule_eval_repo = RuleEvaluationResultRepository(db)
        eval_results = await rule_eval_repo.get_by_project_id(body.project_id)
        crawl_results = [r for r in eval_results if str(r.crawl_id) == str(crawl_id)]

        if not crawl_results:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No rule evaluation results found for project_id={body.project_id}. "
                       f"Run POST /audit/evaluate/{crawl_id} first.",
            )

        scorer = AnalysisScorerService(db)
        unified = await scorer.score_project(body.project_id, crawl_id, force=body.force)

        logger.info(
            f"POST /audit/score/{crawl_id} - "
            f"score={unified['summary']['overall_score']}, "
            f"health={unified['summary']['health']}"
        )

        return unified

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            f"POST /audit/score/{crawl_id}: unexpected error - {exc}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred during scoring",
        )
