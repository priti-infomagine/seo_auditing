"""Tests for summary module (PageSummary / AuditSummary)."""
from __future__ import annotations

from app.modules.category_check.core_seo.models import RuleResult, Severity
from app.modules.category_check.core_seo.summary import (
    AuditSummary,
    PageSummary,
    summarize_audit,
    summarize_page,
)


def _make_result(rule_id: str, passed: bool) -> RuleResult:
    return RuleResult(
        rule_id=rule_id,
        name=f"Rule {rule_id}",
        passed=passed,
        severity=(Severity.PASSED.value if passed else Severity.WARNING.value),
        message="test",
    )


class TestSummarizePage:
    def test_all_pass(self, rule_data):
        from app.modules.category_check.core_seo.rules.checks import TitleTagPresentRule

        rule = TitleTagPresentRule()
        results = rule.evaluate(rule_data)
        summary = summarize_page(results)

        assert summary.passed == 1
        assert summary.failed == 0
        assert summary.total == 1
        assert summary.pass_percentage == 100.0

    def test_all_fail(self):
        results = [_make_result(f"r{i}", False) for i in range(5)]
        summary = summarize_page(results)

        assert summary.passed == 0
        assert summary.failed == 5
        assert summary.total == 5
        assert summary.pass_percentage == 0.0

    def test_mixed(self):
        results = [_make_result(f"r{i}", True) for i in range(17)] + \
                  [_make_result(f"r{i}", False) for i in range(2)]
        summary = summarize_page(results)

        assert summary.passed == 17
        assert summary.failed == 2
        assert summary.total == 19
        assert summary.pass_percentage == round(17 / 19 * 100, 1)

    def test_empty(self):
        summary = summarize_page([])
        assert summary.passed == 0
        assert summary.failed == 0
        assert summary.total == 0
        assert summary.pass_percentage == 0.0

    def test_rule_results_preserved(self):
        results = [_make_result("a", True), _make_result("b", False)]
        summary = summarize_page(results)
        assert len(summary.rule_results) == 2
        assert summary.rule_results[0].rule_id == "a"
        assert summary.rule_results[1].rule_id == "b"


class TestSummarizeAudit:
    def test_single_page(self):
        page1 = PageSummary(passed=15, failed=3, total=18, pass_percentage=83.3)
        summary = summarize_audit([page1])

        assert summary.pages_total == 1
        assert summary.pages_done == 1
        assert summary.rules_passed == 15
        assert summary.rules_failed == 3
        assert summary.pass_percentage == round(15 / 18 * 100, 1)

    def test_multiple_pages(self):
        pages = [
            PageSummary(passed=15, failed=3, total=18, pass_percentage=83.3),
            PageSummary(passed=17, failed=1, total=18, pass_percentage=94.4),
        ]
        summary = summarize_audit(pages)

        assert summary.pages_total == 2
        assert summary.pages_done == 2
        assert summary.rules_passed == 32
        assert summary.rules_failed == 4
        assert summary.pass_percentage == round(32 / 36 * 100, 1)

    def test_empty(self):
        summary = summarize_audit([])
        assert summary.pages_total == 0
        assert summary.pages_done == 0
        assert summary.rules_passed == 0
        assert summary.rules_failed == 0
        assert summary.pass_percentage == 0.0

    def test_pass_percentage_100(self):
        pages = [PageSummary(passed=18, failed=0, total=18, pass_percentage=100.0)]
        summary = summarize_audit(pages)
        assert summary.pass_percentage == 100.0
