"""
POST /audit/score/{crawl_id} — Score SEO analysis for a crawl.

Reads rule evaluation results from PostgreSQL, computes per-page and
project-level scores, persists to seo_analysis_runs, and writes the
output JSON file to app/output/.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.core.database import get_db
from app.core.logger import logger
from app.core.security import get_current_user
from app.modules.audit.schemas.analysis_schemas import (
    ScoreTriggerRequest,
    SeoAnalysisResponse,
)
from app.modules.audit.services.analysis_scorer_service import AnalysisScorerService
from app.modules.crawler.repositories.crawl_job_repository import CrawlJobRepository
from app.modules.audit.repositories.seo_analysis_repository import SeoAnalysisRunRepository
from app.modules.audit.repositories.rule_evaluation_repository import RuleEvaluationResultRepository
from app.modules.auth.models.users import User

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
    current_user: User = Depends(get_current_user),
) -> SeoAnalysisResponse:
    """
    Trigger full scoring for a crawl with completed evaluation.

    Args:
        crawl_id: The crawl job ID.
        body: Request with project_id and force flag.
        db: Database session.
        current_user: Authenticated user.

    Returns:
        SeoAnalysisResponse with full score breakdown.

    Raises:
        HTTPException 404: No rule results or crawl job.
        HTTPException 409: Already scored and force=False.
    """
    logger.info(
        f"POST /audit/score/{crawl_id} - "
        f"project_id={body.project_id}, user_id={current_user.id}"
    )

    try:
        # Load crawl job
        job_repo = CrawlJobRepository(db)
        job = await job_repo.get_by_id(crawl_id)
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Crawl job {crawl_id} not found",
            )

        # Verify ownership
        if str(job.user_id) != str(current_user.id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this crawl job",
            )

        # Check for existing analysis (idempotent)
        analysis_repo = SeoAnalysisRunRepository(db)
        existing = await analysis_repo.get_by_project_id(body.project_id)

        if existing and existing.analysis_status == "completed" and not body.force:
            logger.info(
                f"POST /audit/score/{crawl_id}: returning cached result for project_id={body.project_id}"
            )
            return await _build_response(existing, db, body.project_id, crawl_id)

        # Check that rule evaluation results exist
        rule_eval_repo = RuleEvaluationResultRepository(db)
        eval_results = await rule_eval_repo.get_by_project_id(body.project_id)
        crawl_results = [r for r in eval_results if str(r.crawl_id) == str(crawl_id)]

        if not crawl_results:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No rule evaluation results found for project_id={body.project_id}. "
                       f"Run POST /audit/evaluate/{crawl_id} first.",
            )

        # Run scorer
        scorer = AnalysisScorerService(db)
        result = await scorer.score_project(body.project_id, crawl_id, force=body.force)

        logger.info(
            f"POST /audit/score/{crawl_id} - "
            f"score={result['overall_score']}, grade={result['grade']}"
        )

        # Fetch the persisted run to build response
        run = await analysis_repo.get_by_project_id(body.project_id)
        if run:
            return await _build_response(run, db, body.project_id, crawl_id)

        return SeoAnalysisResponse(
            project_id=result["project_id"],
            crawl_id=result["crawl_id"],
            domain=result["domain"],
            overall_score=result["overall_score"],
            grade=result["grade"],
            total_pages_scored=result["total_pages_scored"],
            total_rules_evaluated=result["total_rules_evaluated"],
            total_passed=result["total_passed"],
            total_failed=result["total_failed"],
            critical_issues=result["critical_issues"],
            warnings=result["warnings"],
            error_pages=result["error_pages"],
            error_summary=result["error_summary"],
            summary=result["summary"],
            category_scores=result["category_scores"],
            top_issues=result["top_issues"],
            per_page=[],
            output_file_path=result["output_file_path"],
            scored_at=result["scored_at"],
            analysis_status="completed",
        )

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


async def _build_response(
    run,
    db: AsyncSession,
    project_id: UUID,
    crawl_id: UUID,
) -> SeoAnalysisResponse:
    """Build SeoAnalysisResponse from a SeoAnalysisRun model + per-page data."""
    # Load per-page scores
    rule_eval_repo = RuleEvaluationResultRepository(db)
    all_results = await rule_eval_repo.get_by_project_id(project_id)
    crawl_results = [r for r in all_results if str(r.crawl_id) == str(crawl_id)]

    # Group by page
    from collections import defaultdict
    page_groups = defaultdict(list)
    for er in crawl_results:
        page_groups[er.page_id].append(er)

    # Load page URLs
    page_repo = CrawlJobRepository(db)  # reuse for lookup
    from app.modules.crawler.repositories.crawl_page_repository import CrawlPageRepository
    crawl_page_repo = CrawlPageRepository(db)
    pages = await crawl_page_repo.get_by_crawl_id(crawl_id)
    page_url_map = {p.id: p.url or p.normalized_url for p in pages}
    homepage_ids = {p.id for p in pages if p.depth == 0}

    per_page = []
    calculator = __import__(
        "app.modules.scorer.services.score_calculator", fromlist=["ScoreCalculator"]
    ).ScoreCalculator()

    for page_id, results in page_groups.items():
        from app.modules.rule_engine.models.rule_result import RuleResult as RR, Severity
        rule_results = [
            RR(
                rule_id=r.rule_id,
                name=r.rule_name,
                category=r.category,
                severity=Severity(r.severity),
                passed=r.passed,
                score_impact=r.score_impact,
                message=r.message,
                recommendation=r.recommendation,
                data=r.rule_data,
                tags=r.tags or [],
            )
            for r in results
        ]
        scorable = [r for r in rule_results if r.severity != Severity.ERROR]
        if scorable:
            page_score = calculator.calculate_score(scorable)
        else:
            page_score = {"overall_score": 0.0, "grade": "F", "total_passed": 0, "total_failed": len(rule_results), "critical_issues": 0}

        per_page.append({
            "page_id": str(page_id),
            "url": page_url_map.get(page_id, str(page_id)),
            "overall_score": page_score.get("overall_score", 0.0),
            "grade": page_score.get("grade", "F"),
            "rules_passed": page_score.get("total_passed", 0),
            "rules_failed": page_score.get("total_failed", 0),
            "critical_issues": page_score.get("critical_issues", 0),
        })

    return SeoAnalysisResponse(
        project_id=str(run.project_id),
        crawl_id=str(run.crawl_id),
        domain=run.domain,
        overall_score=float(run.overall_score) if run.overall_score else 0.0,
        grade=run.grade or "F",
        total_pages_scored=run.total_pages_scored,
        total_rules_evaluated=run.total_rules_evaluated,
        total_passed=run.total_passed,
        total_failed=run.total_failed,
        critical_issues=run.critical_issues,
        warnings=run.warnings,
        error_pages=run.error_pages,
        error_summary=run.error_summary,
        summary=run.summary or "",
        category_scores=run.category_scores or {},
        top_issues=run.top_issues or [],
        per_page=per_page,
        output_file_path=run.output_file_path,
        scored_at=run.scored_at.isoformat() if run.scored_at else None,
        analysis_status=run.analysis_status,
    )
