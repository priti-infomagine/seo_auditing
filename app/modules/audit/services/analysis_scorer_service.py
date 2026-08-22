"""
AnalysisScorerService - Aggregates rule results into project-level SEO scores.

Reads RuleEvaluationResult rows from PostgreSQL, delegates response assembly to
AuditResponseBuilder (which reconstructs RuleResults, runs ScoreCalculator with
homepage weighting, and converts each result to a standardized SEOIssue).

Persists the scalar summary to `seo_analysis_runs` and writes the unified JSON
output file to `app/output/{domain}_{project_id}.json`.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import to_iso, utc_now
from app.core.logger import logger
from app.modules.audit.models.seo_analysis_runs import SeoAnalysisRun
from app.modules.crawler.repositories.crawl_job_repository import CrawlJobRepository
from app.modules.audit.repositories.seo_analysis_repository import SeoAnalysisRunRepository
from app.modules.audit.services.audit_response_builder import AuditResponseBuilder
from app.modules.scorer.services.score_calculator import ScoreCalculator
from app.shared.exceptions import ScoringError


class AnalysisScorerService:
    """
    Aggregates rule results into crawl-level scores, persists to DB and
    writes the output JSON file to ``app/output/{domain}_{project_id}.json``.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.analysis_repo = SeoAnalysisRunRepository(db)
        self.crawl_job_repo = CrawlJobRepository(db)
        self.calculator = ScoreCalculator()

    async def score_project(
        self,
        project_id: UUID,
        crawl_id: UUID,
        force: bool = False,
    ) -> Dict[str, Any]:
        """
        Run the full scoring pipeline for a completed crawl's rule results.

        Delegates response assembly to AuditResponseBuilder, persists a
        SeoAnalysisRun scalar summary, and writes the unified JSON file.

        Args:
            project_id: The project tracking key.
            crawl_id: The crawl job ID.
            force: Kept for API compatibility (caching is handled by the caller).

        Returns:
            The unified audit response dict (see audit_response_schemas.UnifiedAuditResponse).
        """
        try:
            logger.info(
                f"AnalysisScorerService.score_project: project_id={project_id}, "
                f"crawl_id={crawl_id}, force={force}"
            )

            crawl_job = await self.crawl_job_repo.get_by_id(crawl_id)
            if not crawl_job:
                raise ScoringError(f"CrawlJob not found: crawl_id={crawl_id}")

            # Single assembly point for the unified response.
            builder = AuditResponseBuilder(self.db)
            unified: Dict[str, Any] = await builder.build(project_id, crawl_id)

            scored_at = utc_now()
            overall = unified["summary"]["overall_score"]
            grade = self.calculator._get_grade(overall)

            # Persist scalar summary to SeoAnalysisRun.
            run = SeoAnalysisRun(
                project_id=project_id,
                crawl_id=crawl_id,
                domain=unified["audit"].get("domain") or crawl_job.domain,
                overall_score=overall,
                grade=grade,
                total_pages_scored=unified["audit"]["pages_analyzed"],
                total_rules_evaluated=unified["metadata"]["rules_executed"],
                total_passed=unified["summary"]["passed_checks"],
                total_failed=unified["summary"]["failed_checks"],
                critical_issues=unified["summary"]["critical_issues"],
                warnings=(
                    unified["summary"]["high_issues"]
                    + unified["summary"]["medium_issues"]
                    + unified["summary"]["low_issues"]
                ),
                error_pages=len({e.get("page_id") for e in unified["errors"] if e.get("page_id")}),
                error_summary={"errors": unified["errors"]} if unified["errors"] else None,
                category_scores={
                    "tier_counts": {
                        "critical": unified["summary"]["critical_issues"],
                        "high": unified["summary"]["high_issues"],
                        "medium": unified["summary"]["medium_issues"],
                        "low": unified["summary"]["low_issues"],
                    },
                    "categories": unified["categories"],
                },
                top_issues=unified["issues"],
                summary=f"SEO audit scored: {overall}/100 (Grade {grade}).",
                analysis_status="completed",
                scored_at=scored_at,
            )

            # Write unified JSON output file.
            run.output_file_path = await self._write_output_file(
                project_id, crawl_id, run.domain, unified
            )

            await self.analysis_repo.upsert(run)

            logger.info(
                f"AnalysisScorerService.score_project: "
                f"score={overall}, grade={grade}, "
                f"pages={unified['audit']['pages_analyzed']}, "
                f"project_id={project_id}"
            )

            return unified

        except ScoringError:
            raise
        except Exception as exc:
            logger.error(
                f"AnalysisScorerService.score_project: unhandled error "
                f"for project_id={project_id}: {exc}",
                exc_info=True,
            )
            raise ScoringError(f"Project scoring failed: {exc}") from exc

    async def _write_output_file(
        self,
        project_id: UUID,
        crawl_id: UUID,
        domain: str,
        unified: Dict[str, Any],
    ) -> str:
        """Write the unified analysis result to the output folder."""
        try:
            output_dir = Path("app/output")
            output_dir.mkdir(parents=True, exist_ok=True)

            filename = f"{domain}_{project_id}.json"
            filepath = output_dir / filename

            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(unified, f, indent=2, ensure_ascii=False, default=_json_serializer)

            latest_path = output_dir / f"{domain}_latest.json"
            with open(latest_path, "w", encoding="utf-8") as f:
                json.dump(unified, f, indent=2, ensure_ascii=False, default=_json_serializer)

            return str(filepath)

        except Exception as exc:
            logger.error(
                f"Failed to write output file for domain={domain}, project_id={project_id}: {exc}",
                exc_info=True,
            )
            return ""


def _json_serializer(obj):
    from datetime import datetime

    if isinstance(obj, datetime):
        return to_iso(obj)
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")
