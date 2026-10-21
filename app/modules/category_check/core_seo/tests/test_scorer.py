"""Tests for ScoreCalculator and Scorer."""
from __future__ import annotations

from app.modules.category_check.core_seo.models import (
    PageScore,
    RuleResult,
)
from app.modules.category_check.core_seo.rules.checks import TitleTagPresentRule
from app.modules.category_check.core_seo.scorer import ScoreCalculator, Scorer


class TestScoreCalculator:
    def test_calculate_page_score_all_pass(self, rule_data):
        registry_results = []
        for rule_cls in [TitleTagPresentRule]:
            rule = rule_cls()
            registry_results.extend(rule.evaluate(rule_data))

        calc = ScoreCalculator()
        result = calc.calculate_page_score(registry_results, "https://example.com")

        assert result.url == "https://example.com"
        assert result.passed > 0
        assert result.failed == 0
        assert result.score > 0

    def test_calculate_page_score_with_failures(self):
        calc = ScoreCalculator()
        results = [
            RuleResult(
                rule_id="on_page_001",
                name="Title Present",
                category="on_page",
                passed=False,
                severity="warning",
                score_impact=-6,
            ),
            RuleResult(
                rule_id="technical_001",
                name="Canonical",
                category="technical",
                passed=True,
                severity="passed",
                score_impact=0,
            ),
        ]
        page_score = calc.calculate_page_score(results, "https://example.com")

        assert page_score.failed == 1
        assert page_score.passed == 1
        assert page_score.on_page_score < 100
        assert page_score.technical_score == 100.0

    def test_calculate_category_scores(self):
        calc = ScoreCalculator()
        page_scores = [
            PageScore(url="https://a.com", score=90, overall_score=90, on_page_score=85, technical_score=95, passed=16, failed=2),
            PageScore(url="https://b.com", score=80, overall_score=80, on_page_score=70, technical_score=90, passed=15, failed=3),
        ]
        categories = calc.calculate_category_scores(page_scores)

        assert len(categories) == 2
        cat_names = {c.category for c in categories}
        assert cat_names == {"on_page", "technical"}

    def test_calculate_overall_score(self):
        calc = ScoreCalculator()
        page_scores = [
            PageScore(url="a", score=90, overall_score=90),
            PageScore(url="b", score=70, overall_score=70),
        ]
        overall = calc.calculate_overall_score(page_scores)
        assert overall == 80.0

    def test_calculate_overall_score_empty(self):
        calc = ScoreCalculator()
        assert calc.calculate_overall_score([]) == 0.0

    def test_determine_grade_a(self):
        calc = ScoreCalculator()
        assert calc.determine_grade(95) == "A"

    def test_determine_grade_b(self):
        calc = ScoreCalculator()
        assert calc.determine_grade(85) == "B"

    def test_determine_grade_f(self):
        calc = ScoreCalculator()
        assert calc.determine_grade(30) == "F"


class TestScorer:
    def test_score_page(self, rule_data):
        from app.modules.category_check.core_seo.rules.registry import default_registry
        scorer = Scorer()
        registry = default_registry()
        results = registry.run_all(rule_data)
        page_score = scorer.score_page("https://example.com", results)

        assert page_score.url == "https://example.com"
        assert isinstance(page_score.score, float)
        assert page_score.total_rules == 18
        assert page_score.passed + page_score.failed == 18

    def test_score_audit(self):
        scorer = Scorer()
        page_scores = [
            PageScore(url="a", score=90, overall_score=90, passed=17, failed=1),
            PageScore(url="b", score=85, overall_score=85, passed=16, failed=2),
        ]
        audit_summary = scorer.score_audit(page_scores)

        assert "overall_score" in audit_summary
        assert "grade" in audit_summary
        assert audit_summary["page_count"] == 2
        assert audit_summary["overall_score"] == 87.5
