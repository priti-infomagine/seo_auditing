"""
Unit tests for RuleResultToSEOIssueConverter.

Validates the single normalization boundary that turns rule engine output
into the standardized SEOIssue (4-tier severity + affected_part + evidence).
No DB / network required.
"""
import pytest

from app.modules.rule_engine.models.rule_result import RuleResult, Severity
from app.modules.rule_engine.models.seo_issue import SeverityTier
from app.modules.rule_engine.services.issue_factory import RuleResultToSEOIssueConverter


def _mk(rid, sev, passed, cat="on_page"):
    return RuleResult(
        rule_id=rid, name=rid, category=cat,
        severity=sev if isinstance(sev, Severity) else Severity(sev),
        passed=passed, score_impact=-5.0, message="msg",
        recommendation="rec", data={"k": "v"}, tags=[],
    )


@pytest.fixture
def converter():
    return RuleResultToSEOIssueConverter()


def test_critical_maps_to_critical(converter):
    issue = converter.from_rule_result(_mk("on_page_001", Severity.CRITICAL, False), "http://x/a")
    assert issue.severity == SeverityTier.CRITICAL


def test_warning_high_impact_maps_to_high(converter):
    issue = converter.from_rule_result(_mk("content_001", Severity.WARNING, False), "http://x/a")
    assert issue.severity == SeverityTier.HIGH


def test_warning_non_high_impact_maps_to_medium(converter):
    issue = converter.from_rule_result(_mk("links_001", Severity.WARNING, False), "http://x/a")
    assert issue.severity == SeverityTier.MEDIUM


def test_info_maps_to_low(converter):
    issue = converter.from_rule_result(_mk("on_page_005", Severity.INFO, False), "http://x/a")
    assert issue.severity == SeverityTier.LOW


def test_error_returns_none(converter):
    assert converter.from_rule_result(_mk("on_page_001", Severity.ERROR, False), "http://x/a") is None


def test_passed_status(converter):
    issue = converter.from_rule_result(_mk("on_page_001", Severity.CRITICAL, True), "http://x/a")
    assert issue.status == "passed"


def test_failed_status(converter):
    issue = converter.from_rule_result(_mk("on_page_001", Severity.CRITICAL, False), "http://x/a")
    assert issue.status == "failed"


def test_affected_part_known(converter):
    issue = converter.from_rule_result(_mk("on_page_002", Severity.WARNING, False), "http://x/a")
    assert issue.affected_part == "meta_description"


def test_affected_part_unknown(converter):
    issue = converter.from_rule_result(_mk("zzz_999", Severity.WARNING, False), "http://x/a")
    assert issue.affected_part == "unknown"


def test_field_propagation(converter):
    issue = converter.from_rule_result(
        _mk("technical_001", Severity.CRITICAL, False, cat="technical"),
        "http://x/page", page_id="p-1", crawl_id="c-1", project_id="pr-1",
    )
    assert issue.page_url == "http://x/page"
    assert issue.category == "technical"
    assert issue.score_impact == -5.0
    assert issue.evidence == {"k": "v"}
    assert issue.affected_part == "ssl_certificate"
