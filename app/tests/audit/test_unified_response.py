"""
Unit tests for the unified audit response assembly.

Tests AuditResponseBuilder's pure (non-DB) methods: summary, issues, and
categories. A stub DB session is supplied so the constructor can be
instantiated without a real database.
"""
from collections import defaultdict

import pytest

from app.modules.audit.services.audit_response_builder import AuditResponseBuilder
from app.modules.rule_engine.models.rule_result import RuleResult, Severity
from app.modules.rule_engine.services.issue_factory import RuleResultToSEOIssueConverter


def _mk(rid, sev, passed, cat="on_page"):
    return RuleResult(
        rule_id=rid, name=rid, category=cat,
        severity=sev if isinstance(sev, Severity) else Severity(sev),
        passed=passed, score_impact=-5.0, message="m", recommendation="r",
        data={"d": 1}, tags=[],
    )


@pytest.fixture
def builder():
    b = AuditResponseBuilder.__new__(AuditResponseBuilder)
    b.db = None
    b.calculator = None
    b.converter = RuleResultToSEOIssueConverter()
    return b


def _issues():
    c = RuleResultToSEOIssueConverter()
    return [i for i in [
        c.from_rule_result(_mk("on_page_001", Severity.CRITICAL, False), "http://x/a"),
        c.from_rule_result(_mk("on_page_002", Severity.WARNING, False), "http://x/a"),
        c.from_rule_result(_mk("content_001", Severity.WARNING, False), "http://x/b"),
        c.from_rule_result(_mk("images_006", Severity.INFO, False), "http://x/c"),
        c.from_rule_result(_mk("on_page_003", Severity.PASSED, True), "http://x/a"),
    ] if i]


def _cat_checks(issues):
    cat_checks = defaultdict(set)
    for i in issues:
        cat_checks[i.category].add(i.rule_id)
    return cat_checks


def test_summary_tier_counts(builder):
    issues = _issues()
    s = builder._build_summary(85.0, issues)
    assert s["score"] == 85.0
    assert s["health"] == "excellent"
    assert s["issues"]["critical"] == 1
    assert s["issues"]["high"] == 1
    assert s["issues"]["medium"] == 1
    assert s["issues"]["low"] == 1
    assert s["checks"]["passed"] == 1
    assert s["checks"]["failed"] == 4


def test_summary_health_thresholds(builder):
    only_pass = _issues()[-1:]
    assert builder._build_summary(95.0, only_pass)["score"] == 95.0
    assert builder._build_summary(95.0, only_pass)["health"] == "excellent"
    assert builder._build_summary(82.0, only_pass)["score"] == 82.0
    assert builder._build_summary(82.0, only_pass)["health"] == "good"
    assert builder._build_summary(75.0, only_pass)["score"] == 75.0
    assert builder._build_summary(75.0, only_pass)["health"] == "good"
    assert builder._build_summary(59.0, only_pass)["score"] == 59.0
    assert builder._build_summary(59.0, only_pass)["health"] == "poor"
    assert builder._build_summary(39.0, only_pass)["score"] == 39.0
    assert builder._build_summary(39.0, only_pass)["health"] == "critical"


def test_issues_enriched_shape(builder):
    issues = builder._build_issues(_issues())
    expected_keys = {"rule_id", "category", "severity", "title", "why", "what",
                     "recommendation", "llm_tips", "affected_pages", "pages"}
    for i in issues:
        assert set(i.keys()) == expected_keys
    assert len(issues) == 4
    assert all(isinstance(i["rule_id"], str) for i in issues)
    for i in issues:
        assert all("current_value" in p and "evidence" in p for p in i["pages"])


def test_categories_pass_rate_invariant(builder):
    issues = _issues()
    cats = builder._build_categories(issues, _cat_checks(issues), defaultdict(dict), 3)
    for c in cats:
        assert c["checks_total"] == c["checks_passed"] + c["checks_failed"]
        assert c["status"] in ("excellent", "good", "needs_improvement", "poor", "critical", "not_available")
        assert "issues" not in c
