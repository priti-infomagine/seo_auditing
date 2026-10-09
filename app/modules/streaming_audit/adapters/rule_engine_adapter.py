from __future__ import annotations

from typing import Any

from app.modules.scorer.services.scorer_service import ScorerService


class RuleEngineAdapter:
    """Adapter around the existing rule-based evaluation layer."""

    def __init__(self):
        self.scorer_service = ScorerService()

    async def evaluate(self, parsed_data: dict[str, Any]) -> dict[str, Any]:
        score_report = await self.scorer_service.score_parsed_data(parsed_data)
        return {
            "overall_score": score_report.get("overall_score", 0),
            "grade": score_report.get("grade"),
            "category_scores": score_report.get("category_scores", {}),
            "passed_checks": score_report.get("passed_checks", 0),
            "failed_checks": score_report.get("failed_checks", 0),
            "warnings": score_report.get("warnings", []),
            "issues": score_report.get("issues", []),
            "rule_results": score_report.get("rule_results", []),
        }
