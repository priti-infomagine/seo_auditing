"""
Pure unit tests for ``AuditReadModelService`` helpers and projection logic.

These tests use stub objects (not a real DB) and cover the deterministic
parts of the new compact read layer:

* impact tier mapping
* severity / impact sort key
* top-issue grouping and ordering
* max-10 cap, max-3 sample cap
* issue_id derivation / parsing
* zero-issue audit produces an empty top_issues list
* category aggregation (no per-category issue objects)

Additive — does not touch any existing test, schema, or builder.
"""
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.modules.audit.schemas.audit_summary_schemas import (
    AuditOverview,
    CategorySummary,
    IssuePageSample,
    IssueTierCounts,
    PagesBlock,
    TopIssueSummary,
)
from app.modules.audit.schemas.issue_detail_schemas import (
    AffectedSummary,
    EvidenceImage,
    EvidenceItem,
    EvidenceLink,
    IssueDetailResponse,
    IssueEvidenceResponse,
    IssueListResponse,
    IssuePageRow,
    IssuePagesResponse,
    PageDetailResponse,
    RuleMeta,
)
from app.modules.audit.services.audit_read_model_service import AuditReadModelService


# --------------------------------------------------------------------- helpers


def _mk_result(rule_id, category, severity, score_impact, message, page_id=None):
    return SimpleNamespace(
        rule_id=rule_id,
        category=category,
        severity=severity,
        score_impact=score_impact,
        message=message,
        page_id=page_id or "00000000-0000-0000-0000-000000000001",
        rule_name=rule_id,
        passed=False,
    )


def _stub_audit_repo():
    """A bare-bones stub that satisfies the service's helper calls."""
    return SimpleNamespace(
        resolve_audit=lambda audit_id: (None, None),
        load_compact_inputs=lambda audit_id: None,
        crawl_page_repo=SimpleNamespace(get_by_ids=lambda ids: {}),
        seo_repo=SimpleNamespace(get_by_page_id=lambda pid: None),
        network_repo=SimpleNamespace(get_by_page_id=lambda pid: None),
        parsed_fact_repo=SimpleNamespace(
            get_by_page_id=lambda audit_id, page_id: None,
            get_by_page_ids=lambda page_ids: {},
        ),
        rule_eval_repo=SimpleNamespace(),
    )


# --------------------------------------------------------------------- impact / sort


def test_impact_tier_thresholds():
    s = AuditReadModelService.__new__(AuditReadModelService)
    assert s._impact_tier(0.0) == "low"
    assert s._impact_tier(-5.0) == "low"
    assert s._impact_tier(-8.0) == "medium"
    assert s._impact_tier(-14.0) == "medium"
    assert s._impact_tier(-15.0) == "high"
    assert s._impact_tier(-100.0) == "high"
    assert s._impact_tier(20.0) == "high"  # absolute value


def test_severity_rank_orders_correctly():
    s = AuditReadModelService.__new__(AuditReadModelService)
    assert s._severity_rank("critical") < s._severity_rank("high")
    assert s._severity_rank("high") < s._severity_rank("medium")
    assert s._severity_rank("medium") < s._severity_rank("low")
    assert s._severity_rank("unknown") > s._severity_rank("low")


def test_issue_id_round_trip():
    s = AuditReadModelService.__new__(AuditReadModelService)
    # Simulate crawl_id + rule_id with colons in the rule_id
    crawl_id = "11111111-1111-1111-1111-111111111111"
    rule_id = "a:b:c"
    full = s._derive_issue_id(crawl_id, rule_id)
    assert ":" in full
    parsed = s._parse_issue_id(full)
    assert parsed == rule_id


def test_parse_issue_id_without_colon_returns_whole():
    s = AuditReadModelService.__new__(AuditReadModelService)
    assert s._parse_issue_id("noseparator") == "noseparator"


# --------------------------------------------------------------------- grouping


def test_group_failed_results_promotes_worst_severity():
    s = AuditReadModelService.__new__(AuditReadModelService)
    rows = [
        _mk_result("on_page_001", "on_page", "low", -1.0, "msg1", page_id="p1"),
        _mk_result("on_page_001", "on_page", "critical", -2.0, "msg2", page_id="p2"),
        _mk_result("on_page_001", "on_page", "medium", -3.0, "msg3", page_id="p3"),
    ]
    groups = s._group_failed_results(rows)
    assert "on_page_001" in groups
    g = groups["on_page_001"]
    assert g["severity"] == "critical"  # worst wins
    assert g["affected_pages"] == 3
    assert g["category"] == "on_page"


def test_group_failed_results_promotes_max_abs_impact():
    s = AuditReadModelService.__new__(AuditReadModelService)
    rows = [
        _mk_result("x", "on_page", "low", -2.0, "m", page_id="p1"),
        _mk_result("x", "on_page", "low", -15.0, "m", page_id="p2"),
    ]
    groups = s._group_failed_results(rows)
    assert groups["x"]["impact"] == "high"


# --------------------------------------------------------------------- pages block


def test_build_pages_block_counts_failed():
    s = AuditReadModelService.__new__(AuditReadModelService)
    pages = [
        SimpleNamespace(is_crawled=True, is_error=False, status_code=200),
        SimpleNamespace(is_crawled=True, is_error=False, status_code=200),
        SimpleNamespace(is_crawled=True, is_error=True, status_code=500),
    ]
    block = s._build_pages_block(pages)
    assert block.crawled == 3
    assert block.failed == 1
    assert block.analyzed == 2


def test_build_pages_block_no_attributes_uses_len():
    s = AuditReadModelService.__new__(AuditReadModelService)
    # Bare objects without the expected attrs should still produce a sane block
    pages = [object(), object()]
    block = s._build_pages_block(pages)
    assert block.crawled == 2
    assert block.failed == 0
    assert block.analyzed == 2


# --------------------------------------------------------------------- top-issue sort


def test_top_issue_sort_orders_by_severity_then_impact_then_pages():
    s = AuditReadModelService.__new__(AuditReadModelService)
    groups = {
        "a": {"severity": "low", "impact": "low", "affected_pages": 100, "rule_id": "a"},
        "b": {"severity": "critical", "impact": "high", "affected_pages": 1, "rule_id": "b"},
        "c": {"severity": "high", "impact": "high", "affected_pages": 50, "rule_id": "c"},
        "d": {"severity": "critical", "impact": "low", "affected_pages": 1, "rule_id": "d"},
    }
    ordered = sorted(groups.values(), key=s._top_issue_sort_key)
    # b (critical/high) before d (critical/low) before c (high/high) before a (low/low)
    assert [g["rule_id"] for g in ordered] == ["b", "d", "c", "a"]


# --------------------------------------------------------------------- overview


def _stub_service_with_overview_inputs(groups, failed_results, *, run=None, job=None, pages=None):
    """Build an AuditReadModelService with stubbed repos and pre-built inputs."""
    service = AuditReadModelService.__new__(AuditReadModelService)
    if run is None:
        run = SimpleNamespace(
            project_id="proj-1", crawl_id="crawl-1", domain="example.com",
            overall_score=72.0, grade="B", total_pages_scored=10,
            total_rules_evaluated=60, total_passed=45, total_failed=15,
            critical_issues=2, warnings=10,
        )
    if pages is None:
        pages = [SimpleNamespace(is_crawled=True, is_error=False, status_code=200) for _ in range(10)]
    if job is None:
        job = SimpleNamespace(
            url="https://example.com", status="completed",
            created_at=None, completed_at=None,
        )

    class _StubRepo:
        def __init__(self, payload):
            self._payload = payload

        async def load_compact_inputs(self, audit_id):
            return self._payload

        async def resolve_audit(self, audit_id):
            return (None, None)

    service.repo = _StubRepo({
        "analysis_run": run,
        "crawl_job": job,
        "crawl_pages": pages,
        "failed_results": failed_results,
    })
    return service


import asyncio


def test_build_overview_caps_top_issues_at_10():
    rows = []
    for i in range(50):
        rows.append(_mk_result(
            rule_id=f"r_{i:03d}", category="on_page", severity="low",
            score_impact=-1.0, message="m", page_id=f"p-{i}",
        ))
    service = _stub_service_with_overview_inputs({}, rows)
    overview = asyncio.run(service.build_overview("crawl-1"))
    assert isinstance(overview, AuditOverview)
    assert len(overview.top_issues) == 10
    # Stable order: by rule_id
    rule_ids = [t.rule_id for t in overview.top_issues]
    assert rule_ids == sorted(rule_ids)


def test_build_overview_caps_samples_at_3():
    rows = [
        _mk_result("r", "on_page", "critical", -20.0, f"msg-{i}", page_id=f"p-{i}")
        for i in range(20)
    ]
    service = _stub_service_with_overview_inputs({}, rows)
    overview = asyncio.run(service.build_overview("crawl-1"))
    assert len(overview.top_issues) == 1
    assert len(overview.top_issues[0].sample) == 3


def test_build_overview_zero_issues_returns_empty():
    # Zero failed results: issues.total must be 0, but checks.failed is sourced
    # from the persisted run's scalar (not from the empty in-memory list).
    # The fixture below returns total_failed=0 from the run to keep them in sync.
    service = _stub_service_with_overview_inputs(
        {},
        [],
        run=SimpleNamespace(
            project_id="proj-1", crawl_id="crawl-1", domain="example.com",
            overall_score=100.0, grade="A+", total_pages_scored=10,
            total_rules_evaluated=60, total_passed=60, total_failed=0,
            critical_issues=0, warnings=0,
        ),
    )
    overview = asyncio.run(service.build_overview("crawl-1"))
    assert overview.top_issues == []
    assert overview.summary.issues.total == 0
    assert overview.summary.issues.critical == 0
    assert overview.summary.checks.failed == 0
    assert overview.summary.checks.passed == 60


def test_build_overview_summary_severity_counts():
    rows = [
        _mk_result("r1", "on_page", "critical", -1.0, "m"),
        _mk_result("r2", "on_page", "high", -1.0, "m"),
        _mk_result("r3", "on_page", "medium", -1.0, "m"),
        _mk_result("r4", "on_page", "low", -1.0, "m"),
    ]
    service = _stub_service_with_overview_inputs({}, rows)
    overview = asyncio.run(service.build_overview("crawl-1"))
    assert overview.summary.issues.critical == 1
    assert overview.summary.issues.high == 1
    assert overview.summary.issues.medium == 1
    assert overview.summary.issues.low == 1
    assert overview.summary.issues.total == 4


def test_build_overview_categories_have_no_nested_issues():
    rows = [
        _mk_result("r1", "on_page", "critical", -1.0, "m"),
        _mk_result("r2", "technical", "high", -1.0, "m"),
    ]
    service = _stub_service_with_overview_inputs({}, rows)
    overview = asyncio.run(service.build_overview("crawl-1"))
    # All 10 categories are emitted (even those with zero failures)
    assert len(overview.categories) == 10
    # The aggregate counts add up
    total_in_categories = sum(c.issues.total for c in overview.categories)
    assert total_in_categories == 2
    # Categories do not embed per-issue objects
    for cat in overview.categories:
        # No nested issue field
        assert not hasattr(cat, "issues_detail")
        # checks_total reflects unique rule_ids seen for the category
        if cat.id == "on_page":
            assert cat.checks_total == 1
            assert cat.issues.critical == 1
        elif cat.id == "technical_seo":
            assert cat.checks_total == 1
            assert cat.issues.high == 1


def test_build_overview_does_not_include_legacy_fields():
    rows = [_mk_result("r1", "on_page", "critical", -1.0, "m")]
    service = _stub_service_with_overview_inputs({}, rows)
    overview = asyncio.run(service.build_overview("crawl-1"))
    payload = overview.model_dump()
    forbidden = ["audit.crawl_stats", "audit.indexation", "audit.performance",
                 "audit.structured_data", "audit.links", "audit.images",
                 "audit.content", "audit.external_dependencies", "audit.meta"]
    # Legacy heavy audit sub-blocks MUST NOT appear
    audit_dict = payload["audit"]
    for k in ("crawl_stats", "indexation", "performance", "structured_data",
              "links", "images", "content", "external_dependencies", "meta"):
        assert k not in audit_dict, f"legacy key {k!r} unexpectedly present"


def test_build_overview_audit_id_is_passed_through():
    rows = []
    service = _stub_service_with_overview_inputs({}, rows)
    overview = asyncio.run(service.build_overview("audit-xyz"))
    assert overview.audit.id == "audit-xyz"


def test_build_overview_lookup_error_when_no_run():
    service = AuditReadModelService.__new__(AuditReadModelService)

    class _Empty:
        async def load_compact_inputs(self, audit_id):
            return None

    service.repo = _Empty()
    with pytest.raises(LookupError):
        asyncio.run(service.build_overview("missing"))


# --------------------------------------------------------------------- schema shape


def test_schema_payload_is_json_serializable_with_no_heavy_keys():
    rows = [_mk_result("r1", "on_page", "critical", -1.0, "m", page_id="p-1")]
    service = _stub_service_with_overview_inputs({}, rows)
    overview = asyncio.run(service.build_overview("crawl-1"))
    payload = overview.model_dump()
    # Top-level overview: no full pages, no raw evidence, no per-page arrays
    for forbidden in ("per_page", "raw_evidence", "all_links", "all_images",
                      "headers", "redirects"):
        assert forbidden not in payload, forbidden
    # audit block: contains only the compact page counts (not full page objects)
    assert "pages" in payload["audit"]  # compact page counts: {crawled, analyzed, failed}
    assert isinstance(payload["audit"]["pages"], dict)
    assert set(payload["audit"]["pages"].keys()) <= {"crawled", "analyzed", "failed"}
    # Heavy legacy audit sub-blocks must not appear
    for k in ("crawl_stats", "indexation", "performance", "structured_data",
              "links", "images", "content", "external_dependencies", "meta"):
        assert k not in payload["audit"], k
    # top_issues is present and bounded
    assert "top_issues" in payload
    assert len(payload["top_issues"]) <= 10
    for issue in payload["top_issues"]:
        assert len(issue["sample"]) <= 3
    # Each top issue exposes only the compact fields (no nested pages, no evidence)
    compact_issue_keys = set(payload["top_issues"][0].keys())
    assert "rule_id" in compact_issue_keys
    assert "category" in compact_issue_keys
    assert "severity" in compact_issue_keys
    assert "impact" in compact_issue_keys
    assert "affected_pages" in compact_issue_keys
    assert "sample" in compact_issue_keys
    for forbidden_issue_key in ("pages", "evidence", "current_value", "llm_tips",
                                "recommendation", "why", "what", "title"):
        assert forbidden_issue_key not in compact_issue_keys, forbidden_issue_key
