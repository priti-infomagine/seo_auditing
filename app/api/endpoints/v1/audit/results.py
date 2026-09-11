"""
GET /audit/result/{audit_id} — Fetch analysis result for an audit.
GET /audit/history — Fetch analysis history.
GET /audit/status/{audit_id} — Fetch pipeline stage status.
GET /audit/pipeline/{audit_id} — Fetch full pipeline summary.
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Literal, Optional, Union
from uuid import UUID

from app.core.database import get_db
from app.core.logger import logger
from app.modules.audit.services.audit_read_model_service import AuditReadModelService
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
from app.modules.audit.schemas.audit_summary_schemas import AuditOverview
from app.modules.audit.repositories.seo_analysis_repository import SeoAnalysisRunRepository
from app.modules.audit.repositories.parsed_page_fact_repository import ParsedPageFactRepository
from app.modules.audit.repositories.rule_evaluation_repository import RuleEvaluationResultRepository
from app.modules.crawler.repositories.crawl_job_repository import CrawlJobRepository

router = APIRouter()


# Response model union for the format switch.
_AuditResultResponse = Union[SeoAnalysisResponse, AuditOverview]


@router.get(
    "/result/{audit_id}",
    response_model=_AuditResultResponse,
    summary="Fetch analysis result for an audit",
    description=(
        "Returns the SEO analysis result for a given audit_id (== crawl_id). "
        "Use ``?format=full`` (default) to get the legacy unified response with "
        "per-page evidence, or ``?format=compact`` to get the small "
        "``AuditOverview`` projection."
    ),
)
async def get_analysis_result(
    audit_id: UUID,
    format: Literal["full", "compact"] = Query(
        "full",
        description=(
            "Response shape. 'full' (default) = legacy UnifiedAuditResponse "
            "with per-page evidence. 'compact' = new compact AuditOverview."
        ),
    ),
    db: AsyncSession = Depends(get_db),
) -> _AuditResultResponse:
    """Fetch the existing analysis result for an audit."""
    logger.info(f"GET /audit/result/{audit_id} - format={format}")

    try:
        job_repo = CrawlJobRepository(db)
        job = await job_repo.get_by_id(audit_id)
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Crawl job {audit_id} not found",
            )

        analysis_repo = SeoAnalysisRunRepository(db)
        run = await analysis_repo.get_by_audit_id(audit_id)
        if not run:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No analysis run found for audit_id={audit_id}",
            )

        if format == "compact":
            return await AuditReadModelService(db).build_overview(audit_id)

        builder = AuditResponseBuilder(db)
        unified = await builder.build(audit_id)
        return unified

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            f"GET /audit/result/{audit_id}: unexpected error - {exc}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred fetching analysis result",
        )


@router.get(
    "/result/{audit_id}",
    summary="Fetch full analysis result by audit_id (public alias)",
    description="Public endpoint that takes an audit_id and returns the audit response.",
)
async def get_analysis_result_by_project(
    audit_id: UUID,
    format: Literal["full", "compact"] = Query(
        "full",
        description="Response shape. 'full' (default) or 'compact'.",
    ),
    db: AsyncSession = Depends(get_db),
):
    """Fetch the audit response by audit_id (no auth required)."""
    return await get_analysis_result(audit_id=audit_id, format=format, db=db)


@router.get(
    "/history",
    response_model=PaginatedAnalyses,
    summary="Fetch analysis history",
    description="Returns paginated list of analysis runs.",
)
async def get_analysis_history(
    audit_id: Optional[UUID] = Query(None, description="Filter by audit_id"),
    domain: Optional[str] = Query(None, description="Filter by domain"),
    limit: int = Query(20, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> PaginatedAnalyses:
    """Fetch analysis history."""
    logger.info(f"GET /audit/history - limit={limit}, offset={offset}")

    try:
        analysis_repo = SeoAnalysisRunRepository(db)

        if audit_id:
            run = await analysis_repo.get_by_audit_id(audit_id)
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

        runs = await analysis_repo.get_all(limit=limit, offset=offset)
        summaries = [_run_to_summary(r) for r in runs]

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
        audit_id=str(run.audit_id),
        crawl_id=str(run.audit_id),
        domain=run.domain,
        overall_score=float(run.overall_score) if run.overall_score else 0.0,
        grade=run.grade or "F",
        total_pages_scored=run.total_pages_scored,
        critical_issues=run.critical_issues,
        scored_at=run.scored_at.isoformat() if run.scored_at else None,
    )


@router.get(
    "/status/{audit_id}",
    response_model=PipelineStatusResponse,
    summary="Fetch pipeline stage status (public)",
    description="Returns the status of parse, evaluate, and score stages for an audit.",
)
async def get_pipeline_status(
    audit_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> PipelineStatusResponse:
    """Fetch the current status of all pipeline stages for an audit."""
    logger.info(f"GET /audit/status/{audit_id}")

    try:
        job_repo = CrawlJobRepository(db)
        job = await job_repo.get_by_id(audit_id)

        parsed_repo = ParsedPageFactRepository(db)
        parsed_facts = await parsed_repo.get_by_audit_id(audit_id)
        pages_parsed = len(parsed_facts)
        parse_status = "completed" if pages_parsed > 0 else "missing"

        rule_repo = RuleEvaluationResultRepository(db)
        rule_results = await rule_repo.get_by_audit_id(audit_id)
        rules_evaluated = len(rule_results)
        if rules_evaluated > 0:
            evaluate_status = "completed"
        elif pages_parsed > 0:
            evaluate_status = "pending"
        else:
            evaluate_status = "missing"

        analysis_repo = SeoAnalysisRunRepository(db)
        run = await analysis_repo.get_by_audit_id(audit_id)
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
            audit_id=str(audit_id),
            crawl_id=str(audit_id),
            parse_status=parse_status,
            evaluate_status=evaluate_status,
            score_status=score_status,
            pages_parsed=pages_parsed,
            rules_evaluated=rules_evaluated,
            overall_score=overall_score,
            grade=grade,
            output_file_path=output_file_path,
            crawl_config_recovered=job.crawl_config_recovered if job else False,
            crawl_config_recovery_note=(
                "original crawl parameters could not be recovered; used defaults (max_pages=100, max_depth=5)"
                if job and job.crawl_config_recovered
                else None
            ),
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            f"GET /audit/status/{audit_id}: unexpected error - {exc}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred fetching pipeline status",
        )


@router.get(
    "/pipeline/{audit_id}",
    response_model=PipelineSummaryResponse,
    summary="Fetch full pipeline summary",
    description="Returns a comprehensive summary of all pipeline stages for an audit.",
)
async def get_pipeline_summary(
    audit_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> PipelineSummaryResponse:
    """Fetch comprehensive pipeline summary for an audit."""
    logger.info(f"GET /audit/pipeline/{audit_id}")

    try:
        domain = None
        job_repo = CrawlJobRepository(db)
        job = await job_repo.get_by_id(audit_id)
        if job:
            domain = job.domain

        parsed_repo = ParsedPageFactRepository(db)
        parse_facts = await parsed_repo.get_by_audit_id(audit_id)
        parse_count = len(parse_facts)
        parse_stage = ParseStageSummary(
            status="completed" if parse_count > 0 else "missing",
            count=parse_count,
        )

        rule_repo = RuleEvaluationResultRepository(db)
        eval_results = await rule_repo.get_by_audit_id(audit_id)
        eval_count = len(eval_results)
        eval_stage = EvaluateStageSummary(
            status="completed" if eval_count > 0 else "missing",
            count=eval_count,
            rules_run=eval_count // max(1, parse_count) if parse_count else 0,
        )

        analysis_repo = SeoAnalysisRunRepository(db)
        run = await analysis_repo.get_by_audit_id(audit_id)
        if run:
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
            audit_id=str(audit_id),
            crawl_id=str(audit_id),
            domain=domain,
            parse=parse_stage,
            evaluate=eval_stage,
            score=score_stage,
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            f"GET /audit/pipeline/{audit_id}: unexpected error - {exc}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred fetching pipeline summary",
        )
