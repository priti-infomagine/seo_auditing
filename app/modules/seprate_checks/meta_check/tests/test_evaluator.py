from app.modules.seprate_checks.meta_check.evaluator import evaluate_page, evaluate_site


def _page(**overrides):
    page = {
        "status_code": 200,
        "content_type": "text/html",
        "title": "A useful title for the example page",
        "meta_description": "A useful description for the example page that explains the page clearly.",
    }
    page.update(overrides)
    return page


def test_evaluate_page_reports_missing_metadata():
    findings = evaluate_page(_page(title="", meta_description=""))

    assert {finding["code"] for finding in findings} == {
        "meta_title_missing",
        "meta_description_missing",
    }


def test_evaluate_page_reports_length_violations():
    findings = evaluate_page(_page(title="short", meta_description="tiny"))

    assert {finding["code"] for finding in findings} == {
        "meta_title_too_short",
        "meta_description_too_short",
    }


def test_evaluate_site_reports_duplicate_metadata():
    pages = [
        _page(url="https://example.com/one"),
        _page(url="https://example.com/two"),
    ]
    for page in pages:
        page["findings"] = []

    findings, summary, overall_status, severity = evaluate_site(pages)

    assert {finding["code"] for finding in findings} == {
        "duplicate_meta_title",
        "duplicate_meta_description",
    }
    assert summary["total_findings"] == 2
    assert overall_status == "warning"
    assert severity == "medium"


def test_evaluate_page_reports_fetch_failure():
    findings = evaluate_page({"status_code": 503, "error": "Service unavailable"})

    assert findings[0]["code"] == "page_fetch_failed"
    assert findings[0]["status"] == "fail"