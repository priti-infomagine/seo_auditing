"""
AnalysisScorerService - Aggregates rule results into project-level SEO scores.

Reads RuleEvaluationResult rows from PostgreSQL, delegates response assembly to
AuditResponseBuilder (which reconstructs RuleResults, runs ScoreCalculator with
homepage weighting, and converts each result to a standardized SEOIssue).

Persists the scalar summary to `seo_analysis_runs` and writes the unified JSON
output file to `app/output/{domain}_{audit_id}.json`.
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
        writes the output JSON file to ``app/output/{domain}_{audit_id}.json``.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.analysis_repo = SeoAnalysisRunRepository(db)
        self.crawl_job_repo = CrawlJobRepository(db)
        self.calculator = ScoreCalculator()

    async def score_project(
        self,
        audit_id: UUID,
        force: bool = False,
    ) -> Dict[str, Any]:
        """
        Run the full scoring pipeline for a completed crawl's rule results.

        Delegates response assembly to AuditResponseBuilder, persists a
        SeoAnalysisRun scalar summary, and writes the unified JSON file.

        Args:
            audit_id: The audit ID (== crawl_id), the single tracking key.
            force: Kept for API compatibility (caching is handled by the caller).

        Returns:
            The unified audit response dict (see audit_response_schemas.UnifiedAuditResponse).
        """
        try:
            logger.info(
                f"AnalysisScorerService.score_project: audit_id={audit_id}, "
                f"force={force}"
            )

            crawl_job = await self.crawl_job_repo.get_by_id(audit_id)
            if not crawl_job:
                raise ScoringError(f"CrawlJob not found: audit_id={audit_id}")

            # Single assembly point for the unified response.
            builder = AuditResponseBuilder(self.db)
            unified: Dict[str, Any] = await builder.build(audit_id)

            scored_at = utc_now()
            overall = unified["summary"]["score"]
            grade = self.calculator._get_grade(overall)

            # Persist scalar summary to SeoAnalysisRun.
            run = SeoAnalysisRun(
                audit_id=audit_id,
                domain=unified["audit"].get("domain") or crawl_job.domain,
                overall_score=overall,
                grade=grade,
                total_pages_scored=unified["audit"]["pages"]["analyzed"],
                total_rules_evaluated=unified["audit"]["meta"]["rules_executed"],
                total_passed=unified["summary"]["checks"]["passed"],
                total_failed=unified["summary"]["checks"]["failed"],
                critical_issues=unified["summary"]["issues"]["critical"],
                warnings=(
                    unified["summary"]["issues"]["high"]
                    + unified["summary"]["issues"]["medium"]
                    + unified["summary"]["issues"]["low"]
                ),
                error_pages=len({e.get("page_id") for e in unified["audit"]["errors"] if e.get("page_id")}),
                error_summary={"errors": unified["audit"]["errors"]} if unified["audit"]["errors"] else None,
                category_scores={
                    "tier_counts": {
                        "critical": unified["summary"]["issues"]["critical"],
                        "high": unified["summary"]["issues"]["high"],
                        "medium": unified["summary"]["issues"]["medium"],
                        "low": unified["summary"]["issues"]["low"],
                    },
                    "categories": unified["categories"],
                },
                top_issues={"schema_version": 2, "issues": unified["issues"]},
                summary=f"SEO audit scored: {overall}/100 (Grade {grade}).",
                analysis_status="completed",
                scored_at=scored_at,
            )

            # Write unified JSON output file.
            run.output_file_path = await self._write_output_file(
                audit_id, run.domain, unified
            )

            await self.analysis_repo.upsert(run)

            logger.info(
                f"AnalysisScorerService.score_project: "
                f"score={overall}, grade={grade}, "
                f"pages={unified['audit']['pages']['analyzed']}, "
                f"audit_id={audit_id}"
            )

            return unified

        except ScoringError:
            raise
        except Exception as exc:
            logger.error(
                f"AnalysisScorerService.score_project: unhandled error "
                f"for audit_id={audit_id}: {exc}",
                exc_info=True,
            )
            raise ScoringError(f"Project scoring failed: {exc}") from exc

    async def _write_output_file(
        self,
        audit_id: UUID,
        domain: str,
        unified: Dict[str, Any],
    ) -> str:
        """Write the unified analysis result to the output folder."""
        import asyncio
        import shutil
        import json
        from pathlib import Path

        try:
            output_dir = Path("app/output")
            output_dir.mkdir(parents=True, exist_ok=True)

            filename = f"{domain}_{audit_id}.json"
            filepath = output_dir / filename
            latest_path = output_dir / f"{domain}_latest.json"

            # Serialize once
            json_bytes = json.dumps(
                unified, indent=2, ensure_ascii=False, default=_json_serializer
            ).encode("utf-8")

            # Write primary file off the event loop
            await asyncio.to_thread(filepath.write_bytes, json_bytes)

            # Copy to latest (also off event loop)
            await asyncio.to_thread(shutil.copyfile, filepath, latest_path)

            return str(filepath)

        except Exception as exc:
            logger.error(
                f"Failed to write output file for domain={domain}, audit_id={audit_id}: {exc}",
                exc_info=True,
            )
            return ""


def _json_serializer(obj):
    from datetime import datetime

    if isinstance(obj, datetime):
        return to_iso(obj)
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")
