"""
DB Adapter for Report Generation — builds AuditReportResponse from database rows.

Fetches CrawlJob, CrawlPages, RuleEvaluationResults, and SeoAnalysisRun from DB,
maps rule evaluation rows to CheckResult objects, and delegates report assembly
to report_assembler.build_report_response.
"""
from __future__ import annotations

from uuid import UUID
from typing import Dict

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.datetime_utils import utc_now
from app.core.logger import logger
from app.modules.audit.repositories.rule_evaluation_repository import RuleEvaluationResultRepository
from app.modules.audit.repositories.seo_analysis_repository import SeoAnalysisRunRepository
from app.modules.crawler.repositories.crawl_job_repository import CrawlJobRepository
from app.modules.crawler.repositories.crawl_page_repository import CrawlPageRepository
from app.modules.scorer.report_assembler import build_report_response
from app.schemas.report_schemas import AuditReportResponse, CheckResult


def _per_check_score(passed: bool, score_impact: float) -> float:
    """Derive a 0-100 per-check score from pass/fail + score_impact.

    Mirrors check_result_adapter._per_check_score so the DB adapter path
    populates CheckResult.score the same way the scorer adapter does.
    """
    if passed:
        return 100.0
    return max(0.0, min(100.0, 100.0 + float(score_impact or 0.0)))


async def build_audit_report(db: AsyncSession, audit_id: UUID) -> AuditReportResponse:
    """
    Fetch DB rows for an audit and build an AuditReportResponse.

    Args:
        db: Database session.
        audit_id: Audit identifier (== crawl_id).

    Returns:
        AuditReportResponse object.

    Raises:
        ValueError: If CrawlJob is not found.
    """
    logger.info(f"build_audit_report: fetching data for audit_id={audit_id}")

    job_repo = CrawlJobRepository(db)
    crawl_job = await job_repo.get_by_id(audit_id)
    if not crawl_job:
        raise ValueError(f"CrawlJob not found for audit_id={audit_id}")

    rule_repo = RuleEvaluationResultRepository(db)
    rule_results = await rule_repo.get_by_audit_id(audit_id)

    page_repo = CrawlPageRepository(db)
    crawl_pages = await page_repo.get_by_crawl_id(audit_id)
    page_url_map: Dict[UUID, str] = {p.id: p.url for p in crawl_pages}

    analysis_repo = SeoAnalysisRunRepository(db)
    seo_run = await analysis_repo.get_by_audit_id(audit_id)

    check_results: list[CheckResult] = []
    for r in rule_results:
        check = CheckResult(
            check_id=r.rule_id,
            category=r.category,
            weight=1.0,
            applicable=True,
            passed=r.passed,
            severity=r.severity,
            score_impact=r.score_impact,
            score=_per_check_score(r.passed, r.score_impact),
            page_url=page_url_map.get(r.page_id, crawl_job.url),
            title=r.rule_name,
            description=r.message,
            recommendation=r.recommendation,
            evidence=r.rule_data,
        )
        check_results.append(check)

    site_category = settings.DEFAULT_SITE_CATEGORY

    if seo_run and seo_run.scored_at:
        scanned_at_dt = seo_run.scored_at
    elif crawl_job.completed_at:
        scanned_at_dt = crawl_job.completed_at
    else:
        scanned_at_dt = utc_now()

    scanned_at_str = scanned_at_dt.isoformat()

    report = build_report_response(
        scan_id=str(audit_id),
        url=crawl_job.url,
        site_category=site_category,
        scanned_at=scanned_at_str,
        pages_crawled=crawl_job.pages_crawled,
        check_results=check_results,
    )

    logger.info(
        f"build_audit_report: successfully built report for audit_id={audit_id}, "
        f"score={report.overall_score.value if report.overall_score else 0}"
    )

    return report
