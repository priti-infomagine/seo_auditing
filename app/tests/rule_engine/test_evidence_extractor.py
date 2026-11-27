import asyncio

from app.modules.parser.analyzers.image_analyzer import analyze_images
from app.modules.rule_engine.category_rules.images import BrokenImageDetectionRule
from app.modules.rule_engine.models.rule_result import RuleResult, Severity
from app.modules.rule_engine.services.issue_factory import (
    RuleResultToSEOIssueConverter,
)
from app.modules.rule_engine.services.evidence_extractor import (
    RuleEvidenceExtractor,
)


def _build_image_evidence(rule_data, page_context=None, passed=False):
    return RuleEvidenceExtractor.build(
        rule_id="images_013",
        rule_name="Broken Image Detection",
        category="images",
        passed=passed,
        severity="critical",
        message="Broken image source detected",
        recommendation="Fix or remove the broken image URL",
        page_url="https://moneymatters.co.in/services",
        rule_data=rule_data,
        page_context=page_context,
    )


def test_broken_image_rule_evidence_includes_resource_url_for_fix():
    image_url = "https://moneymatters.co.in/assets/broken-logo.png"
    evidence = _build_image_evidence({
        "broken_count": 1,
        "total_checked": 7,
        "broken_images": [{"url": image_url, "http_status": 404}],
    })

    assert evidence["target"]["url"] == "https://moneymatters.co.in/services"
    assert evidence["target"]["resource_urls"] == [image_url]
    assert evidence["fix_location"]["url"] == "https://moneymatters.co.in/services"
    assert evidence["fix_location"]["resource_urls"] == [image_url]
    assert evidence["source"] == {"kind": "rule_result_data"}
    assert "fields" not in evidence["source"]


def test_broken_image_rule_uses_persisted_page_context_for_resource_url():
    image_url = "https://moneymatters.co.in/assets/missing.png"
    evidence = _build_image_evidence(
        {"broken_count": 1, "total_checked": 2},
        page_context={
            "images": [
                {"tag": "img", "url": image_url, "http_status": 404},
                {"tag": "img", "url": "https://moneymatters.co.in/assets/ok.png", "http_status": 200},
            ],
            "broken_images": [
                {"tag": "img", "url": image_url, "http_status": 404},
            ],
        },
    )

    assert evidence["fix_location"]["resource_urls"] == [image_url]


def test_passing_evidence_has_no_fix_location():
    evidence = _build_image_evidence(
        {"checked": 2},
        passed=True,
    )

    assert evidence["outcome"] == "passed"
    assert "fix_location" not in evidence


def test_image_analysis_returns_bounded_broken_source_details():
    broken = [
        {"tag": "img", "url": f"https://moneymatters.co.in/assets/{index}.png", "http_status": 404}
        for index in range(27)
    ]

    analysis = analyze_images(broken)

    assert analysis["broken_image_count"] == 27
    assert len(analysis["broken_images"]) == 25
    assert analysis["broken_images"][0]["url"] == broken[0]["url"]
    assert analysis["broken_images_truncated"] == 2


def test_broken_image_rule_preserves_source_urls_in_failure_data():
    image_url = "https://moneymatters.co.in/assets/not-found.png"
    result = asyncio.run(BrokenImageDetectionRule().evaluate({
        "images": {
            "broken_image_count": 1,
            "total_count": 1,
            "broken_images": [{"url": image_url, "http_status": 404}],
        },
    }))[0]

    assert result.data["broken_images"][0]["url"] == image_url


def test_issue_conversion_exposes_image_url_in_fix_location():
    image_url = "https://moneymatters.co.in/assets/missing.png"
    result = RuleResult(
        rule_id="images_013",
        name="Broken Image Detection",
        category="images",
        severity=Severity.CRITICAL,
        passed=False,
        score_impact=-3,
        message="1/1 image is broken",
        recommendation="Fix the image URL",
        data={
            "broken_count": 1,
            "total_checked": 1,
            "broken_images": [{"url": image_url, "http_status": 404}],
        },
        tags=[],
    )

    issue = RuleResultToSEOIssueConverter.from_rule_result(
        result,
        page_url="https://moneymatters.co.in/services",
    )

    assert issue.evidence_v1["fix_location"]["url"] == "https://moneymatters.co.in/services"
    assert issue.evidence_v1["fix_location"]["resource_urls"] == [image_url]
