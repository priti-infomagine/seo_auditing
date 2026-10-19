"""
ScoreCalculator — weighted category + page scoring using 18 rules across
on_page (title, meta, headings, content) and technical (canonical, headers,
robots) categories.
"""
from __future__ import annotations

from typing import Any

from .constants import (
    GRADE_THRESHOLDS,
    ON_PAGE_WEIGHT,
    TECHNICAL_WEIGHT,
)
from .models import CategoryScore, PageScore, RuleResult


class ScoreCalculator:
    """Calculates scores for a page or entire audit based on rule results."""

    CATEGORY_MAP: dict[str, str] = {
        "title": "on_page",
        "meta": "on_page",
        "headings": "on_page",
        "content": "on_page",
        "canonical": "technical",
        "technical": "technical",
    }

    def calculate_page_score(
        self,
        rule_results: list[RuleResult],
        url: str,
    ) -> PageScore:
        """Calculate a PageScore from a list of RuleResults.

        Each failed rule contributes its ``score_impact`` (already negative)
        to the corresponding category. The overall page score is the
        weighted average of category scores.
        """
        category_impacts: dict[str, float] = {"on_page": 0.0, "technical": 0.0}
        category_weights: dict[str, int] = {"on_page": 0, "technical": 0}
        rule_scores: dict[str, RuleResult] = {}

        for result in rule_results:
            category = result.category or self.CATEGORY_MAP.get(
                result.rule_id.replace("_", "").replace("rule", "")[:8],
                "on_page",
            )
            if category not in ("on_page", "technical"):
                category = "on_page"

            if not result.passed:
                category_impacts[category] += abs(result.score_impact)

            category_weights[category] += 1
            rule_scores[result.rule_id] = result

        on_page_penalty = category_impacts["on_page"]
        tech_penalty = category_impacts["technical"]

        on_page_score = max(0.0, 100.0 - on_page_penalty)
        technical_score = max(0.0, 100.0 - tech_penalty)

        total_weight = category_weights["on_page"] + category_weights["technical"]
        if total_weight > 0:
            overall_score = (
                on_page_score * ON_PAGE_WEIGHT + technical_score * TECHNICAL_WEIGHT
            ) / total_weight
        else:
            overall_score = 100.0

        overall_score = round(max(0.0, min(100.0, overall_score)), 2)

        return PageScore(
            url=url,
            score=overall_score,
            overall_score=overall_score,
            on_page_score=round(on_page_score, 2),
            technical_score=round(technical_score, 2),
            rule_results={k: v for k, v in rule_scores.items()},
            total_rules=len(rule_results),
            passed=sum(1 for r in rule_results if r.passed),
            failed=sum(1 for r in rule_results if not r.passed),
        )

    def calculate_category_scores(
        self, page_scores: list[PageScore]
    ) -> list[CategoryScore]:
        """Aggregate page scores into per-category CategoryScore objects."""
        on_page_scores = [ps.on_page_score for ps in page_scores if ps.on_page_score is not None]
        technical_scores = [ps.technical_score for ps in page_scores if ps.technical_score is not None]

        categories: list[CategoryScore] = []

        if on_page_scores:
            avg = sum(on_page_scores) / len(on_page_scores)
            total_rules_on_page = sum(ps.total_rules for ps in page_scores)
            passed_rules_on_page = sum(ps.passed for ps in page_scores)
            failed_rules_on_page = total_rules_on_page - passed_rules_on_page
            categories.append(CategoryScore(
                category="on_page",
                score=round(avg, 2),
                max_score=100.0,
                weight=ON_PAGE_WEIGHT,
                rules_checked=total_rules_on_page,
                rules_passed=passed_rules_on_page,
                rules_failed=failed_rules_on_page,
                rule_count=total_rules_on_page,
                passed_rules=passed_rules_on_page,
            ))

        if technical_scores:
            avg = sum(technical_scores) / len(technical_scores)
            total_rules_tech = sum(ps.total_rules for ps in page_scores)
            passed_rules_tech = sum(ps.passed for ps in page_scores)
            failed_rules_tech = total_rules_tech - passed_rules_tech
            categories.append(CategoryScore(
                category="technical",
                score=round(avg, 2),
                max_score=100.0,
                weight=TECHNICAL_WEIGHT,
                rules_checked=total_rules_tech,
                rules_passed=passed_rules_tech,
                rules_failed=failed_rules_tech,
                rule_count=total_rules_tech,
                passed_rules=passed_rules_tech,
            ))

        return categories

    def calculate_overall_score(self, page_scores: list[PageScore]) -> float:
        """Calculate the overall audit score (0–100)."""
        if not page_scores:
            return 0.0

        scores = [ps.score for ps in page_scores if ps.score is not None]
        if not scores:
            return 0.0

        return round(sum(scores) / len(scores), 2)

    def determine_grade(self, score: float) -> str:
        """Determine a letter grade from a numeric score."""
        if score >= GRADE_THRESHOLDS["A"]:
            return "A"
        elif score >= GRADE_THRESHOLDS["B"]:
            return "B"
        elif score >= GRADE_THRESHOLDS["C"]:
            return "C"
        elif score >= GRADE_THRESHOLDS["D"]:
            return "D"
        else:
            return "F"


class Scorer:
    """High-level scorer that orchestrates PageScore and CategoryScore computation."""

    def __init__(self, calculator: ScoreCalculator | None = None):
        self.calculator = calculator or ScoreCalculator()

    def score_page(
        self,
        url: str,
        rule_results: list[RuleResult],
    ) -> PageScore:
        """Score a single page from its rule results."""
        return self.calculator.calculate_page_score(rule_results, url)

    def score_pages(
        self,
        page_results: list[PageScore],
    ) -> list[CategoryScore]:
        """Score and aggregate a list of page results into category scores."""
        return self.calculator.calculate_category_scores(page_results)

    def score_audit(self, page_scores: list[PageScore]) -> dict[str, Any]:
        """Produce an audit-level summary score dict.

        Returns:
            Dict with ``overall_score``, ``grade``, ``categories``,
            ``page_count``, ``pages_with_errors``, ``pages_with_warnings``.
        """
        overall = self.calculator.calculate_overall_score(page_scores)
        grade = self.calculator.determine_grade(overall)
        categories = self.score_pages(page_scores)

        pages_with_errors = 0
        pages_with_warnings = 0
        for ps in page_scores:
            for result in ps.rule_results.values():
                if not result.passed:
                    if result.severity == "critical" or (result.score_impact and result.score_impact <= -8):
                        pages_with_errors += 1
                        break
            else:
                for result in ps.rule_results.values():
                    if not result.passed and result.score_impact and result.score_impact < 0:
                        pages_with_warnings += 1
                        break

        return {
            "overall_score": overall,
            "grade": grade,
            "categories": categories,
            "page_count": len(page_scores),
            "pages_with_errors": pages_with_errors,
            "pages_with_warnings": pages_with_warnings,
        }


__all__ = ["ScoreCalculator", "Scorer"]
