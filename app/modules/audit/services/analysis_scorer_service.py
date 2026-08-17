"""
AnalysisScorerService - Aggregates rule results into project-level SEO scores.

Reads RuleEvaluationResult rows from PostgreSQL, groups by page, computes
per-page and project-level scores using ScoreCalculator, persists to
`seo_analysis_runs`, and writes the output JSON file to `app/output/`.

Fault-tolerant: pages with no rule results are scored as 0 (grade F)
and counted in `error_pages`. The audit is marked `completed` with an
error_summary, only failing on system-level errors.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Dict, Any, List, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import logger
from app.modules.audit.repositories.seo_analysis_repository import SeoAnalysisRunRepository
from app.modules.audit.repositories.rule_evaluation_repository import RuleEvaluationResultRepository
from app.modules.audit.models.seo_analysis_runs import SeoAnalysisRun
from app.modules.crawler.repositories.crawl_job_repository import CrawlJobRepository
from app.modules.crawler.repositories.crawl_page_repository import CrawlPageRepository
from app.modules.scorer.services.score_calculator import ScoreCalculator
from app.modules.rule_engine.models.rule_result import RuleResult, Severity
from app.shared.exceptions import ScoringError


class AnalysisScorerService:
    """
    Aggregates rule results into crawl-level scores, persists to DB and
    writes the output JSON file to ``app/output/{domain}_{project_id}.json``.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.analysis_repo = SeoAnalysisRunRepository(db)
        self.rule_eval_repo = RuleEvaluationResultRepository(db)
        self.crawl_job_repo = CrawlJobRepository(db)
        self.crawl_page_repo = CrawlPageRepository(db)
        self.calculator = ScoreCalculator()

    async def score_project(
        self,
        project_id: UUID,
        crawl_id: UUID,
        force: bool = False,
    ) -> Dict[str, Any]:
        """
        Run the full scoring pipeline for a completed crawl's rule results.

        Steps:
          1. Load CrawlJob → domain
          2. Load all RuleEvaluationResult rows for (project_id, crawl_id)
          3. Group by page_id → per-page scores via ScoreCalculator
          4. Aggregate across pages → project-level overall_score, grade
          5. Build category_scores (weighted across all pages)
          6. Extract top_issues (highest score_impact failures)
          7. Upsert SeoAnalysisRun to DB
          8. Write JSON output file to app/output/{domain}_{project_id}.json
          9. Update analysis_run.output_file_path

        Args:
            project_id: The project tracking key.
            crawl_id: The crawl job ID.
            force: If True, re-score even if analysis exists.

        Returns:
            SeoAnalysisRun model instance (converted to dict).
        """
        try:
            logger.info(
                f"AnalysisScorerService.score_project: project_id={project_id}, "
                f"crawl_id={crawl_id}, force={force}"
            )

            # Load crawl job for domain
            crawl_job = await self.crawl_job_repo.get_by_id(crawl_id)
            if not crawl_job:
                raise ScoringError(f"CrawlJob not found: crawl_id={crawl_id}")

            domain = crawl_job.domain

            # Load rule evaluation results
            eval_results = await self.rule_eval_repo.get_by_project_id(project_id)
            eval_results = [r for r in eval_results if str(r.crawl_id) == str(crawl_id)]

            if not eval_results:
                logger.warning(
                    f"AnalysisScorerService: no rule results found for "
                    f"project_id={project_id}, crawl_id={crawl_id}"
                )
                return await self._create_empty_analysis(
                    project_id, crawl_id, domain
                )

            # Group results by page_id
            page_results: Dict[UUID, List[Any]] = {}
            for er in eval_results:
                pid = er.page_id
                if pid not in page_results:
                    page_results[pid] = []
                page_results[pid].append(
                    RuleResult(
                        rule_id=er.rule_id,
                        name=er.rule_name,
                        category=er.category,
                        severity=Severity(er.severity),
                        passed=er.passed,
                        score_impact=er.score_impact,
                        message=er.message,
                        recommendation=er.recommendation,
                        data=er.rule_data,
                        tags=er.tags or [],
                    )
                )

            # Load crawl pages for URL mapping
            crawl_pages = await self.crawl_page_repo.get_by_crawl_id(crawl_id)
            page_url_map: Dict[UUID, str] = {}
            homepage_ids: set = set()
            for p in crawl_pages:
                page_url_map[p.id] = p.url or p.normalized_url
                if p.depth == 0:
                    homepage_ids.add(p.id)

            # Score each page
            per_page_scores: List[Dict[str, Any]] = []
            all_category_results: Dict[str, List[RuleResult]] = {}
            all_rule_results: List[RuleResult] = []
            error_pages: List[Dict[str, Any]] = []
            rules_with_errors: set = set()

            for page_id, page_rule_results in page_results.items():
                url = page_url_map.get(page_id, str(page_id))

                # Check for evaluation errors (synthetic results)
                has_errors = any(
                    r.severity == Severity.ERROR
                    for r in page_rule_results
                )

                # Filter out error results for scoring (they count as failures with no score impact)
                scorable_results = [
                    r for r in page_rule_results
                    if r.severity != Severity.ERROR
                ]

                for r in page_rule_results:
                    if r.severity == Severity.ERROR:
                        rules_with_errors.add(r.rule_id)

                if not scorable_results:
                    # No scorable rules — mark as error page
                    error_pages.append({
                        "page_id": str(page_id),
                        "url": url,
                        "error": "No scorable rule results",
                    })
                    page_score_dict = {
                        "overall_score": 0.0,
                        "grade": "F",
                    }
                else:
                    # Score this page
                    page_score_dict = self.calculator.calculate_score(scorable_results)

                per_page_scores.append({
                    "page_id": str(page_id),
                    "url": url,
                    "overall_score": page_score_dict["overall_score"],
                    "grade": page_score_dict["grade"],
                    "rules_passed": page_score_dict.get("total_passed", 0),
                    "rules_failed": page_score_dict.get("total_failed", 0),
                    "critical_issues": page_score_dict.get("critical_issues", 0),
                    "rule_results": [self._rule_result_to_dict(r) for r in page_rule_results],
                })

                # Collect category results for aggregate scoring
                categories = page_score_dict.get("categories", {})
                for cat_name, cat_data in categories.items():
                    if cat_name not in all_category_results:
                        all_category_results[cat_name] = []
                    # Reconstruct RuleResults from category data
                    for issue in cat_data.get("issues", []):
                        all_category_results[cat_name].append(
                            self._dict_to_rule_result(issue)
                        )
                    for issue in cat_data.get("warnings", []):
                        all_category_results[cat_name].append(
                            self._dict_to_rule_result(issue)
                        )

                all_rule_results.extend(page_rule_results)

            # Compute aggregate score
            # Weight pages: homepage weight=2.0, others=1.0
            total_weight = 0.0
            weighted_score = 0.0
            total_passed = 0
            total_failed = 0
            total_critical = 0
            total_warnings = 0

            for ps in per_page_scores:
                page_id_obj = UUID(ps["page_id"])
                weight = 2.0 if page_id_obj in homepage_ids else 1.0
                weighted_score += ps["overall_score"] * weight
                total_weight += weight
                total_passed += ps.get("rules_passed", 0)
                total_failed += ps.get("rules_failed", 0)

                # Count severities from rule_results
                for rr in ps.get("rule_results", []):
                    if not rr.get("passed", True):
                        sev = rr.get("severity", "info")
                        if sev == "critical":
                            total_critical += 1
                        elif sev == "warning":
                            total_warnings += 1

            overall_score = round(weighted_score / total_weight, 1) if total_weight > 0 else 0.0
            grade = self.calculator._get_grade(overall_score)

            # Get top issues (across all pages, sorted by score_impact asc = most negative first)
            top_issues = sorted(
                [r for r in all_rule_results
                 if not r.passed and r.severity != Severity.ERROR],
                key=lambda r: r.score_impact,
            )[:10]

            total_rules_evaluated = len(all_rule_results)
            total_passed_rules = sum(1 for r in all_rule_results if r.passed)
            total_failed_rules = total_rules_evaluated - total_passed_rules

            # Build category scores (flat aggregate from calculator)
            category_scores = self._build_category_scores(all_category_results)

            # Build summary
            summary = self._generate_summary(
                overall_score, total_critical, total_warnings,
                total_failed_rules, total_passed_rules,
            )

            # Build error summary
            error_summary = {
                "error_pages": error_pages,
                "rules_with_errors": list(rules_with_errors),
                "total_error_pages": len(error_pages),
            } if error_pages or rules_with_errors else None

            scored_at = datetime.now(timezone.utc)

            # Create SeoAnalysisRun
            run = SeoAnalysisRun(
                project_id=project_id,
                crawl_id=crawl_id,
                domain=domain,
                overall_score=overall_score,
                grade=grade,
                total_pages_scored=len(per_page_scores),
                total_rules_evaluated=total_rules_evaluated,
                total_passed=total_passed_rules,
                total_failed=total_failed_rules,
                critical_issues=total_critical,
                warnings=total_warnings,
                error_pages=len(error_pages),
                error_summary=error_summary,
                category_scores=category_scores,
                top_issues=[self._rule_result_to_dict(r) for r in top_issues],
                summary=summary,
                analysis_status="completed",
                scored_at=scored_at,
            )

            # Write output file
            output_file_path = await self._write_output_file(
                project_id, crawl_id, domain, run, per_page_scores
            )
            run.output_file_path = output_file_path

            # Upsert to DB
            await self.analysis_repo.upsert(run)

            logger.info(
                f"AnalysisScorerService.score_project: "
                f"score={overall_score}, grade={grade}, "
                f"pages={len(per_page_scores)}, "
                f"project_id={project_id}"
            )

            # Return as dict
            return await self._run_to_dict(run)

        except ScoringError:
            raise
        except Exception as exc:
            logger.error(
                f"AnalysisScorerService.score_project: unhandled error "
                f"for project_id={project_id}: {exc}",
                exc_info=True,
            )
            raise ScoringError(f"Project scoring failed: {exc}") from exc

    async def _create_empty_analysis(
        self,
        project_id: UUID,
        crawl_id: UUID,
        domain: str,
    ) -> Dict[str, Any]:
        """Create a minimal analysis run when no rule results exist."""
        try:
            run = SeoAnalysisRun(
                project_id=project_id,
                crawl_id=crawl_id,
                domain=domain,
                overall_score=0.0,
                grade="F",
                total_pages_scored=0,
                total_rules_evaluated=0,
                total_passed=0,
                total_failed=0,
                critical_issues=0,
                warnings=0,
                error_pages=0,
                error_summary={
                    "error_pages": [],
                    "rules_with_errors": [],
                    "total_error_pages": 0,
                    "no_rule_results": True,
                },
                category_scores={},
                top_issues=[],
                summary="No rule evaluation results found. Ensure parsing and evaluation completed successfully.",
                analysis_status="completed",
                scored_at=datetime.now(timezone.utc),
            )

            output_file_path = await self._write_output_file(
                project_id, crawl_id, domain, run, []
            )
            run.output_file_path = output_file_path

            await self.analysis_repo.upsert(run)
            return await self._run_to_dict(run)
        except Exception as exc:
            logger.error(f"Failed to create empty analysis: {exc}", exc_info=True)
            raise ScoringError(f"Failed to create empty analysis: {exc}") from exc

    async def _write_output_file(
        self,
        project_id: UUID,
        crawl_id: UUID,
        domain: str,
        run: SeoAnalysisRun,
        per_page: List[Dict[str, Any]],
    ) -> str:
        """Write the analysis result to the output folder."""
        try:
            output_dir = Path("app/output")
            output_dir.mkdir(parents=True, exist_ok=True)

            filename = f"{domain}_{project_id}.json"
            filepath = output_dir / filename

            # Load full rule results for output
            rule_results = await self.rule_eval_repo.get_by_project_id(project_id)
            rule_results = [r for r in rule_results if str(r.crawl_id) == str(crawl_id)]

            output = {
                "project_id": str(project_id),
                "crawl_id": str(crawl_id),
                "domain": domain,
                "scored_at": run.scored_at.isoformat() if run.scored_at else None,
                "overall_score": run.overall_score,
                "grade": run.grade,
                "total_pages_scored": run.total_pages_scored,
                "total_rules_evaluated": run.total_rules_evaluated,
                "total_passed": run.total_passed,
                "total_failed": run.total_failed,
                "critical_issues": run.critical_issues,
                "warnings": run.warnings,
                "error_pages": run.error_pages,
                "error_summary": run.error_summary,
                "summary": run.summary,
                "category_scores": run.category_scores,
                "top_issues": run.top_issues,
                "per_page": per_page,
            }

            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(output, f, indent=2, ensure_ascii=False, default=str)

            # Also write latest copy
            latest_path = output_dir / f"{domain}_latest.json"
            with open(latest_path, "w", encoding="utf-8") as f:
                json.dump(output, f, indent=2, ensure_ascii=False, default=str)

            return str(filepath)

        except Exception as exc:
            logger.error(
                f"Failed to write output file for domain={domain}, project_id={project_id}: {exc}",
                exc_info=True,
            )
            return ""

    def _build_category_scores(
        self,
        all_category_results: Dict[str, List[RuleResult]],
    ) -> Dict[str, Any]:
        """Build aggregate category scores from all pages' results."""
        category_scores: Dict[str, Any] = {}
        for cat_name, cat_results in all_category_results.items():
            if not cat_results:
                continue
            score_dict = self.calculator.calculate_score(cat_results)
            category_scores[cat_name] = score_dict
        return category_scores

    def _rule_result_to_dict(self, rr: RuleResult) -> Dict[str, Any]:
        """Convert a RuleResult to a dict for JSON serialization."""
        return {
            "rule_id": rr.rule_id,
            "name": rr.name,
            "category": rr.category,
            "severity": rr.severity.value if hasattr(rr.severity, "value") else rr.severity,
            "passed": rr.passed,
            "score_impact": rr.score_impact,
            "message": rr.message,
            "recommendation": rr.recommendation,
            "data": rr.data,
            "tags": rr.tags,
        }

    def _dict_to_rule_result(self, d: Dict[str, Any]) -> RuleResult:
        """Reconstruct a RuleResult from a dict (from category scores)."""
        return RuleResult(
            rule_id=d.get("rule_id", ""),
            name=d.get("name", ""),
            category=d.get("category", ""),
            severity=Severity(d.get("severity", "info")),
            passed=d.get("passed", True),
            score_impact=d.get("score_impact", 0.0),
            message=d.get("message", ""),
            recommendation=d.get("recommendation"),
            data=d.get("data"),
            tags=d.get("tags", []),
        )

    def _generate_summary(
        self,
        score: float,
        critical: int,
        warnings: int,
        failed: int,
        passed: int,
    ) -> str:
        """Generate human-readable summary."""
        grade = self.calculator._get_grade(score)
        if score >= 90:
            return f"Excellent! Your site scores {score:.1f}/100 (Grade {grade}). Your website follows SEO best practices."
        elif score >= 80:
            return f"Good! Your site scores {score:.1f}/100 (Grade {grade}). Minor improvements recommended."
        elif score >= 70:
            return f"Fair. Your site scores {score:.1f}/100 (Grade {grade}). {warnings} warnings and {critical} critical issues need attention."
        elif score >= 60:
            return f"Poor. Your site scores {score:.1f}/100 (Grade {grade}). Significant improvements needed ({critical} critical issues)."
        else:
            return f"Critical. Your site scores {score:.1f}/100 (Grade {grade}). Major SEO issues require immediate attention."

    async def _run_to_dict(self, run: SeoAnalysisRun) -> Dict[str, Any]:
        """Convert SeoAnalysisRun to a response dict."""
        return {
            "project_id": str(run.project_id),
            "crawl_id": str(run.crawl_id),
            "domain": run.domain,
            "overall_score": float(run.overall_score) if run.overall_score is not None else 0.0,
            "grade": run.grade or "F",
            "total_pages_scored": run.total_pages_scored,
            "total_rules_evaluated": run.total_rules_evaluated,
            "total_passed": run.total_passed,
            "total_failed": run.total_failed,
            "critical_issues": run.critical_issues,
            "warnings": run.warnings,
            "error_pages": run.error_pages,
            "error_summary": run.error_summary,
            "summary": run.summary or "",
            "category_scores": run.category_scores or {},
            "top_issues": run.top_issues or [],
            "output_file_path": run.output_file_path,
            "scored_at": run.scored_at.isoformat() if run.scored_at else None,
            "analysis_status": run.analysis_status,
        }
