"""
Tests for the report-assembly layer (app/modules/scorer/report_assembler.py).

These are pure, synchronous tests: no database, no network, no LLM. They validate the
reshaping contract — ordering, applicability, issue grouping across pages, facts+proof
population, and error sanitization — directly from build_report_response.
"""
from __future__ import annotations

from app.modules.scorer.report_assembler import build_report_response
from app.modules.scorer.services.score_calculator import CATEGORY_ORDER
from app.schemas.report_schemas import AuditReportResponse, Category, CheckResult


def _make_check(**overrides):
    base = dict(
        check_id="x_000",
        category="on_page",
        weight=1.0,
        applicable=True,
        passed=False,
        severity="warning",
        score_impact=-5.0,
        score=95.0,
        category_score=90.0,
        category_grade="B",
        overall_value=88.0,
        overall_grade="B",
        page_url="https://example.com/",
        title="Some Check",
        description="Something looked wrong",
    )
    base.update(overrides)
    return CheckResult(**base)


def _build(checks, site_category="ecommerce"):
    return build_report_response(
        scan_id="scan_1",
        url="https://example.com",
        site_category=site_category,
        scanned_at="2026-08-19T10:00:00Z",
        pages_crawled=2 if any(c.page_url.endswith("/page1") or c.page_url.endswith("/page2") for c in checks) else 1,
        check_results=checks,
    )


def _cats_by_id(report: AuditReportResponse) -> dict:
    return {c.id: c for c in report.categories}


def test_categories_emitted_in_config_order():
    report = _build([])
    ids = [c.id for c in report.categories]
    # overall_summary is skipped; remaining ids sorted ascending by CATEGORY_ORDER.
    assert "overall_summary" not in ids
    expected = [cid for cid in sorted(CATEGORY_ORDER, key=lambda k: CATEGORY_ORDER[k]) if cid != "overall_summary"]
    assert ids == expected


def test_local_seo_not_applicable_for_ecommerce():
    report = _build([], site_category="ecommerce")
    local = _cats_by_id(report)["local_seo"]
    assert local.applicable is False
    assert local.score is None
    assert local.reason_not_applicable is not None
    assert "ecommerce" in local.reason_not_applicable


def test_local_seo_applicable_for_local_business():
    checks = [_make_check(check_id="l_1", category="local_seo", applicable=True,
                          passed=False, severity="warning", score_impact=-2,
                          score=98, category_score=99.0, category_grade="A")]
    report = _build(checks, site_category="local_business")
    local = _cats_by_id(report)["local_seo"]
    assert local.applicable is True
    assert local.score is not None


def test_issue_grouping_across_pages():
    checks = [
        _make_check(check_id="t_002", category="technical", page_url="https://example.com/page1"),
        _make_check(check_id="t_002", category="technical", page_url="https://example.com/page2"),
    ]
    report = _build(checks)
    tech = _cats_by_id(report)["technical_seo"]
    t_issues = [i for i in tech.issues if i.check_id == "t_002"]
    assert len(t_issues) == 1
    issue = t_issues[0]
    assert issue.affected_page_count == 2
    assert {p.url for p in issue.affected_pages} == {
        "https://example.com/page1",
        "https://example.com/page2",
    }


def test_issue_ids_sequential_and_stable():
    checks = [
        _make_check(check_id="a_1", category="on_page", severity="critical", score_impact=-15),
        _make_check(check_id="b_1", category="on_page", severity="warning", score_impact=-5),
    ]
    report = _build(checks)
    ids = [i.issue_id for c in report.categories for i in c.issues]
    assert ids == ["iss_0001", "iss_0002"]


def test_priority_sorting_within_category():
    checks = [
        _make_check(check_id="low_00", category="on_page", severity="info", score_impact=-1),
        _make_check(check_id="high_00", category="on_page", severity="critical", score_impact=-15),
    ]
    report = _build(checks)
    issues = _cats_by_id(report)["on_page_seo"].issues
    assert [i.priority for i in issues] == ["high", "low"]


def test_issues_carry_facts_and_proof():
    checks = [
        _make_check(
            check_id="img_001", category="images", severity="warning", score_impact=-4,
            found_value={"without_alt": 3, "total": 10, "coverage": 70.0},
            expected_value="100% alt-text coverage",
            evidence={"without_alt": 3, "sample": [{"src": "/a.png", "alt": ""}]},
        ),
    ]
    report = _build(checks)
    issue = _cats_by_id(report)["images"].issues[0]
    assert issue.affected_page_count == 1
    page = issue.affected_pages[0]
    assert page.url == "https://example.com/"
    assert page.found_value["without_alt"] == 3
    assert page.expected_value == "100% alt-text coverage"
    assert page.evidence["sample"][0]["src"] == "/a.png"


def test_error_severity_is_sanitized():
    checks = [
        _make_check(
            check_id="sec_001", category="security", severity="error",
            score_impact=-3.0,
            description="Rule evaluation failed: KeyError('strict-transport-security')",
            recommendation="Check rule implementation for data mismatch",
        ),
    ]
    report = _build(checks)
    issue = _cats_by_id(report)["security"].issues[0]
    assert issue.severity == "warning"          # 'error' must not leak into output
    assert issue.priority == "high"             # rule-infra failure stays high priority
    assert "KeyError" not in issue.description
    assert "rule evaluation failed" not in issue.description.lower()
    assert "could not be fully evaluated" in issue.description


def test_overall_score_passes_through_compute_value():
    checks = [_make_check(check_id="a_1", category="on_page", overall_value=95.5, overall_grade="A")]
    report = _build(checks)
    assert report.overall_score.value == 95.5
    assert report.overall_score.grade == "A"


def test_overall_score_falls_back_to_category_aggregation():
    checks = [
        _make_check(check_id="a_1", category="on_page", overall_value=None, overall_grade=None,
                    category_score=80.0, weight=2.0),
        _make_check(check_id="b_1", category="technical", overall_value=None, overall_grade=None,
                    category_score=60.0, weight=1.0),
    ]
    report = _build(checks)
    # (80*2 + 60*1) / 3 = 73.33
    assert report.overall_score.value == round((80.0 * 2.0 + 60.0 * 1.0) / 3.0, 1)


def test_excluded_vs_applicable_counts():
    checks = [
        _make_check(check_id="ok_1", category="on_page", applicable=True, passed=True, severity="passed",
                    score_impact=1, score=100),
        _make_check(check_id="no_1", category="local_seo", applicable=False, passed=False, severity="warning",
                    score_impact=-1, score=99),
    ]
    report = _build(checks, site_category="ecommerce")
    os = report.overall_score
    assert os.checks_run == 2
    assert os.checks_applicable == 1
    assert os.checks_excluded == 1
    assert os.passed == 1


def test_passed_checks_do_not_produce_issues():
    checks = [
        _make_check(check_id="ok_1", category="on_page", applicable=True, passed=True,
                    severity="passed", score_impact=1, score=100,
                    description="All good", recommendation=None),
    ]
    report = _build(checks)
    on_page = _cats_by_id(report)["on_page_seo"]
    assert on_page.issues == []
    assert on_page.issue_count is not None
    assert on_page.issue_count.critical == 0
    assert on_page.issue_count.warning == 0
    assert on_page.issue_count.info == 0
