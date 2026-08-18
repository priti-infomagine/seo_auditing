"""
GET /audit/result/{crawl_id} — Fetch analysis result for a crawl.
GET /audit/history — Fetch analysis history.
GET /audit/status/{project_id} — Fetch pipeline stage status.
GET /audit/pipeline/{project_id} — Fetch full pipeline summary.
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from typing import List, Optional

from app.core.database import get_db
from app.core.logger import logger
from app.core.security import get_current_user
from app.modules.audit.services.audit_response_builder import AuditResponseBuilder
from app.modules.audit.schemas.analysis_schemas import (
    SeoAnalysisResponse,
    PaginatedAnalyses,
    PipelineStatusResponse,
    PipelineSummaryResponse,
    ParseStageSummary,
    EvaluateStageSummary,
    ScoreStageSummary,
)
from app.modules.audit.repositories.seo_analysis_repository import SeoAnalysisRunRepository
from app.modules.audit.repositories.parsed_page_fact_repository import ParsedPageFactRepository
from app.modules.audit.repositories.rule_evaluation_repository import RuleEvaluationResultRepository
from app.modules.crawler.repositories.crawl_job_repository import CrawlJobRepository
from app.modules.auth.models.users import User

router = APIRouter()


@router.get(
    "/result/{crawl_id}",
    response_model=SeoAnalysisResponse,
    summary="Fetch analysis result for a crawl",
    description="Returns the full SEO analysis result (score, categories, per-page breakdown) for a given crawl_id and project_id.",
)
async def get_analysis_result(
    crawl_id: UUID,
    project_id: UUID = Query(..., description="Project identifier"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SeoAnalysisResponse:
    """Fetch the existing analysis result for a crawl."""
    logger.info(
        f"GET /audit/result/{crawl_id} - project_id={project_id}, user_id={current_user.id}"
    )

    try:
        # Verify crawl job ownership
        job_repo = CrawlJobRepository(db)
        job = await job_repo.get_by_id(crawl_id)
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Crawl job {crawl_id} not found",
            )
        if str(job.user_id) != str(current_user.id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this crawl job",
            )

        # Load analysis run
        analysis_repo = SeoAnalysisRunRepository(db)
        run = await analysis_repo.get_by_project_id(project_id)
        if not run or str(run.crawl_id) != str(crawl_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No analysis run found for project_id={project_id}",
            )

        # Rebuild the unified response from persisted DB rows
        builder = AuditResponseBuilder(db)
        unified = await builder.build(project_id, crawl_id)
        return unified

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            f"GET /audit/result/{crawl_id}: unexpected error - {exc}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred fetching analysis result",
        )


@router.get(
    "/history",
    response_model=PaginatedAnalyses,
    summary="Fetch analysis history",
    description="Returns paginated list of analysis runs for the current user.",
)
async def get_analysis_history(
    project_id: Optional[UUID] = Query(None, description="Filter by project_id"),
    domain: Optional[str] = Query(None, description="Filter by domain"),
    limit: int = Query(20, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PaginatedAnalyses:
    """Fetch analysis history for the current user."""
    logger.info(
        f"GET /audit/history - user_id={current_user.id}, limit={limit}, offset={offset}"
    )

    try:
        analysis_repo = SeoAnalysisRunRepository(db)

        if project_id:
            # Single project
            run = await analysis_repo.get_by_project_id(project_id)
            summaries = [_run_to_summary(run)] if run else []
            return PaginatedAnalyses(
                total=len(summaries),
                limit=limit,
                offset=offset,
                results=summaries,
            )

        if domain:
            runs = await analysis_repo.get_by_domain(domain)
            summaries = [_run_to_summary(r) for r in runs]
            summaries = summaries[offset:offset + limit]
            return PaginatedAnalyses(
                total=len(runs),
                limit=limit,
                offset=offset,
                results=summaries,
            )

        # Get all runs for this user via crawl_jobs
        job_repo = CrawlJobRepository(db)
        user_jobs = await job_repo.get_by_user_id(current_user.id)
        user_project_ids = [j.project_id for j in user_jobs if j.project_id]

        runs = await analysis_repo.get_by_user_and_domain(
            domain or "", user_project_ids
        ) if user_project_ids else []

        summaries = [_run_to_summary(r) for r in runs]
        summaries = summaries[offset:offset + limit]

        return PaginatedAnalyses(
            total=len(summaries),
            limit=limit,
            offset=offset,
            results=summaries,
        )

    except Exception as exc:
        logger.error(
            f"GET /audit/history: unexpected error - {exc}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred fetching analysis history",
        )


def _run_to_summary(run):
    """Convert SeoAnalysisRun to SeoAnalysisSummary."""
    from app.modules.audit.schemas.analysis_schemas import SeoAnalysisSummary
    return SeoAnalysisSummary(
        project_id=str(run.project_id),
        crawl_id=str(run.crawl_id),
        domain=run.domain,
        overall_score=float(run.overall_score) if run.overall_score else 0.0,
        grade=run.grade or "F",
        total_pages_scored=run.total_pages_scored,
        critical_issues=run.critical_issues,
        scored_at=run.scored_at.isoformat() if run.scored_at else None,
    )


@router.get(
    "/status/{project_id}",
    response_model=PipelineStatusResponse,
    summary="Fetch pipeline stage status",
    description="Returns the status of parse, evaluate, and score stages for a project.",
)
async def get_pipeline_status(
    project_id: UUID,
    crawl_id: Optional[UUID] = Query(None, description="Crawl ID (optional, auto-detected if omitted)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PipelineStatusResponse:
    """Fetch the current status of all pipeline stages for a project."""
    logger.info(
        f"GET /audit/status/{project_id} - crawl_id={crawl_id}, user_id={current_user.id}"
    )

    try:
        # Verify project ownership via crawl_jobs
        job_repo = CrawlJobRepository(db)

        # Find crawl job for this project+user
        if crawl_id:
            job = await job_repo.get_by_id(crawl_id)
            if not job or str(job.user_id) != str(current_user.id):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied to this project",
                )
            if str(job.project_id) != str(project_id) and job.project_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Project ID does not match this crawl job",
                )
            if not job.project_id:
                job.project_id = project_id
                await job_repo.update(job)

        # Check parsed facts
        parsed_repo = ParsedPageFactRepository(db)
        parsed_facts = await parsed_repo.get_by_project_id(project_id)
        pages_parsed = len(parsed_facts)
        parse_status = "completed" if pages_parsed > 0 else "missing"

        # Check rule results
        rule_repo = RuleEvaluationResultRepository(db)
        rule_results = await rule_repo.get_by_project_id(project_id)
        rules_evaluated = len(rule_results)
        if rules_evaluated > 0:
            evaluate_status = "completed"
        elif pages_parsed > 0:
            evaluate_status = "pending"
        else:
            evaluate_status = "missing"

        # Check analysis run
        analysis_repo = SeoAnalysisRunRepository(db)
        run = await analysis_repo.get_by_project_id(project_id)
        score_status = "missing"
        overall_score = None
        grade = None
        output_file_path = None
        if run:
            score_status = run.analysis_status or "missing"
            overall_score = float(run.overall_score) if run.overall_score else None
            grade = run.grade
            output_file_path = run.output_file_path

        return PipelineStatusResponse(
            project_id=str(project_id),
            crawl_id=str(crawl_id) if crawl_id else "",
            parse_status=parse_status,
            evaluate_status=evaluate_status,
            score_status=score_status,
            pages_parsed=pages_parsed,
            rules_evaluated=rules_evaluated,
            overall_score=overall_score,
            grade=grade,
            output_file_path=output_file_path,
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            f"GET /audit/status/{project_id}: unexpected error - {exc}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred fetching pipeline status",
        )


@router.get(
    "/pipeline/{project_id}",
    response_model=PipelineSummaryResponse,
    summary="Fetch full pipeline summary",
    description="Returns a comprehensive summary of all pipeline stages for a project.",
)
async def get_pipeline_summary(
    project_id: UUID,
    crawl_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PipelineSummaryResponse:
    """Fetch comprehensive pipeline summary for a project."""
    logger.info(
        f"GET /audit/pipeline/{project_id} - crawl_id={crawl_id}, user_id={current_user.id}"
    )

    try:
        # Verify ownership
        job_repo = CrawlJobRepository(db)
        job = await job_repo.get_by_id(crawl_id)
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Crawl job {crawl_id} not found",
            )
        if str(job.user_id) != str(current_user.id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this crawl job",
            )

        domain = job.domain

        # Parse stage
        parsed_repo = ParsedPageFactRepository(db)
        parse_facts = await parsed_repo.get_by_crawl_id(crawl_id)
        parse_facts = [f for f in parse_facts if str(f.project_id) == str(project_id)]
        parse_count = len(parse_facts)
        parse_stage = ParseStageSummary(
            status="completed" if parse_count > 0 else "missing",
            count=parse_count,
        )

        # Evaluate stage
        rule_repo = RuleEvaluationResultRepository(db)
        eval_results = await rule_repo.get_by_project_id(project_id)
        eval_count = len([r for r in eval_results if str(r.crawl_id) == str(crawl_id)])
        eval_stage = EvaluateStageSummary(
            status="completed" if eval_count > 0 else "missing",
            count=eval_count,
            rules_run=len([r for r in eval_results if r.crawl_id == crawl_id]) // max(1, parse_count) if parse_count else 0,
        )

        # Score stage
        analysis_repo = SeoAnalysisRunRepository(db)
        run = await analysis_repo.get_by_project_id(project_id)
        if run and str(run.crawl_id) == str(crawl_id):
            score_stage = ScoreStageSummary(
                status=run.analysis_status or "missing",
                count=run.total_rules_evaluated,
                overall_score=float(run.overall_score) if run.overall_score else None,
                grade=run.grade,
                total_pages_scored=run.total_pages_scored,
                critical_issues=run.critical_issues,
                output_file_path=run.output_file_path,
            )
        else:
            score_stage = ScoreStageSummary(status="missing", count=0)

        return PipelineSummaryResponse(
            project_id=str(project_id),
            crawl_id=str(crawl_id),
            domain=domain,
            parse=parse_stage,
            evaluate=eval_stage,
            score=score_stage,
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            f"GET /audit/pipeline/{project_id}: unexpected error - {exc}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred fetching pipeline summary",
        )
