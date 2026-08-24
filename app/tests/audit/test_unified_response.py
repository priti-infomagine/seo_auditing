"""
Unit tests for the unified audit response assembly.

Tests AuditResponseBuilder's pure (non-DB) methods: summary, issues, priorities,
category_results, categories, and recommendations. A stub DB session is supplied so the
constructor can be instantiated without a real database.

NOTE: these tests reflect the post-fix contracts:
  * issues[] carries {rule_id, severity, message, page_url, affected_part} (Section 6)
  * status is score-derived via get_status -> excellent/good/poor/critical (Section 4)
  * categories[] pass the checks_total == checks_passed + checks_failed invariant and
    carry an `issues` list only when they have failures (Section 3 / Section 8)
"""
from collections import defaultdict

import pytest

from app.modules.audit.services.audit_response_builder import AuditResponseBuilder
from app.modules.rule_engine.models.rule_evidence_map import SUBCATEGORY_OF
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


def _check_cache(issues):
    """Build the shared check-result cache shape _build_category_results expects."""
    cache = defaultdict(dict)
    for i in issues:
        sub = SUBCATEGORY_OF.get(i.rule_id, i.rule_id)
        cache[i.page_url][sub] = (i.status != "failed")
    return cache


def _cat_checks(issues):
    cat_checks = defaultdict(set)
    for i in issues:
        cat_checks[i.category].add(SUBCATEGORY_OF.get(i.rule_id, i.rule_id))
    return cat_checks


def test_summary_tier_counts(builder):
    issues = _issues()
    s = builder._build_summary(85.0, issues)
    assert s["critical_issues"] == 1
    assert s["high_issues"] == 1      # content_001 WARNING -> high
    assert s["medium_issues"] == 1     # on_page_002 WARNING -> medium
    assert s["low_issues"] == 1       # images_006 INFO -> low
    assert s["passed_checks"] == 1
    assert s["failed_checks"] == 4
    assert s["health"] == "good"


def test_summary_health_thresholds(builder):
    only_pass = _issues()[-1:]  # single passed issue
    assert builder._build_summary(95.0, only_pass)["health"] == "excellent"
    assert builder._build_summary(82.0, only_pass)["health"] == "good"
    assert builder._build_summary(75.0, only_pass)["health"] == "good"
    assert builder._build_summary(59.0, only_pass)["health"] == "poor"
    assert builder._build_summary(39.0, only_pass)["health"] == "critical"


def test_issues_enriched_shape(builder):
    issues = builder._build_issues(_issues())
    for i in issues:
        assert set(i.keys()) == {"rule_id", "severity", "message", "page_url", "affected_part", "current_description", "recommended"}
    assert len(issues) == 4  # passed excluded
    # rule_id scheme is traceable to recommendations[]
    assert all(isinstance(i["rule_id"], str) for i in issues)


def test_priorities_by_tier(builder):
    p = builder._build_priorities(_issues())
    assert set(p["critical"]) == {"on_page_001"}
    assert set(p["high"]) == {"content_001"}
    assert set(p["medium"]) == {"on_page_002"}
    assert set(p["low"]) == {"images_006"}


def test_category_results_pass_rate(builder):
    issues = _issues()
    cr = builder._build_category_results(issues, _check_cache(issues), 3)
    titles = cr["on_page"]["titles"]
    # on_page_001 failed on http://x/a -> 1 affected page of 3
    assert titles["affected_pages"] == 1
    assert titles["score"] == round(100 * (3 - 1) / 3, 1)
    assert titles["status"] == "needs_improvement"  # score-derived (Section 4)
    h1 = cr["on_page"]["h1"]
    assert h1["affected_pages"] == 0
    assert h1["score"] == 100.0
    assert h1["status"] == "excellent"


def test_category_results_all_passed_when_clean(builder):
    cr = builder._build_category_results([], {}, 3)
    for subchecks in cr.values():
        for name, chk in subchecks.items():
            if "status" not in chk:
                continue
            assert chk["status"] == "excellent"
            assert chk["score"] == 100.0
            assert chk["affected_pages"] == 0


def test_category_results_has_status_and_score(builder):
    issues = _issues()
    cr = builder._build_category_results(issues, _check_cache(issues), 3)
    for cat_id, subchecks in cr.items():
        for name, chk in subchecks.items():
            if "status" not in chk:
                assert "available" in chk
                assert chk["available"] is False
                continue
            assert "score" in chk
            assert chk["status"] in ("excellent", "good", "needs_improvement", "poor", "critical", "not_available")


def test_categories_pass_rate_invariant_and_issues(builder):
    issues = _issues()
    cats = builder._build_categories(issues, _cat_checks(issues), _check_cache(issues), 3)
    for c in cats:
        assert c["checks_total"] == c["checks_passed"] + c["checks_failed"]
        assert c["status"] in ("excellent", "good", "needs_improvement", "poor", "critical", "not_available")
    onpage = next(c for c in cats if c["id"] == "on_page")
    assert "issues" in onpage and onpage["issues"]  # has failures -> issues present
    perf = next(c for c in cats if c["id"] == "performance")
    assert "issues" not in perf  # no failures -> key omitted (Section 8)


def test_recommendations_priority_ordering(builder):
    recs = builder._build_recommendations(_issues())
    priorities = [r["priority"] for r in recs]
    assert priorities == sorted(priorities)  # ascending: critical(1) first
    assert recs[0]["rule_id"] == "on_page_001"
    assert recs[0]["priority"] == 1
    assert all({"priority", "rule_id", "title", "action", "effort", "affected_pages"} <= set(r.keys()) for r in recs)
