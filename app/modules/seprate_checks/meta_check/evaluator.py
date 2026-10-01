from collections import Counter
from typing import Any


TITLE_MIN_LENGTH = 30
TITLE_MAX_LENGTH = 60
DESCRIPTION_MIN_LENGTH = 70
DESCRIPTION_MAX_LENGTH = 160


def _finding(
    code: str,
    severity: str,
    status: str,
    message: str,
    evidence: str | None = None,
) -> dict[str, Any]:
    return {
        "code": code,
        "severity": severity,
        "status": status,
        "message": message,
        "evidence": evidence,
    }


def evaluate_page(page: dict[str, Any]) -> list[dict[str, Any]]:
    """Evaluate one crawled page without performing I/O."""
    findings: list[dict[str, Any]] = []
    status_code = page.get("status_code")
    content_type = (page.get("content_type") or "").lower()
    title = (page.get("title") or "").strip()
    description = (page.get("meta_description") or "").strip()

    if page.get("error") or not status_code or status_code >= 400:
        findings.append(_finding(
            "page_fetch_failed", "high", "fail",
            "The page could not be fetched successfully.",
            page.get("error") or f"HTTP {status_code}",
        ))
        return findings

    if content_type and "html" not in content_type:
        findings.append(_finding(
            "page_not_html", "medium", "warning",
            "The URL did not return an HTML document.", content_type,
        ))
        return findings

    if not title:
        findings.append(_finding(
            "meta_title_missing", "high", "fail",
            "The page is missing a title tag.",
        ))
    elif len(title) < TITLE_MIN_LENGTH:
        findings.append(_finding(
            "meta_title_too_short", "low", "warning",
            f"The title is shorter than {TITLE_MIN_LENGTH} characters.",
            f"{len(title)} characters",
        ))
    elif len(title) > TITLE_MAX_LENGTH:
        findings.append(_finding(
            "meta_title_too_long", "medium", "warning",
            f"The title is longer than {TITLE_MAX_LENGTH} characters.",
            f"{len(title)} characters",
        ))

    if not description:
        findings.append(_finding(
            "meta_description_missing", "high", "fail",
            "The page is missing a meta description.",
        ))
    elif len(description) < DESCRIPTION_MIN_LENGTH:
        findings.append(_finding(
            "meta_description_too_short", "low", "warning",
            f"The meta description is shorter than {DESCRIPTION_MIN_LENGTH} characters.",
            f"{len(description)} characters",
        ))
    elif len(description) > DESCRIPTION_MAX_LENGTH:
        findings.append(_finding(
            "meta_description_too_long", "medium", "warning",
            f"The meta description is longer than {DESCRIPTION_MAX_LENGTH} characters.",
            f"{len(description)} characters",
        ))

    return findings


def evaluate_site(pages: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any], str, str]:
    """Add duplicate metadata findings and calculate site-level status."""
    findings: list[dict[str, Any]] = []
    titles = Counter(
        page["title"].strip()
        for page in pages
        if page.get("title") and page["title"].strip()
    )
    descriptions = Counter(
        page["meta_description"].strip()
        for page in pages
        if page.get("meta_description") and page["meta_description"].strip()
    )

    for value, count in titles.items():
        if count > 1:
            findings.append(_finding(
                "duplicate_meta_title", "medium", "warning",
                "The same title is used on multiple pages.",
                f"{count} pages: {value}",
            ))
    for value, count in descriptions.items():
        if count > 1:
            findings.append(_finding(
                "duplicate_meta_description", "medium", "warning",
                "The same meta description is used on multiple pages.",
                f"{count} pages: {value}",
            ))

    page_findings = [finding for page in pages for finding in page.get("findings", [])]
    all_findings = page_findings + findings
    summary = {
        "pages_discovered": len(pages),
        "pages_checked": sum(1 for page in pages if not page.get("error")),
        "pages_failed": sum(1 for page in pages if page.get("error")),
        "missing_titles": sum(any(f["code"] == "meta_title_missing" for f in page.get("findings", [])) for page in pages),
        "missing_descriptions": sum(any(f["code"] == "meta_description_missing" for f in page.get("findings", [])) for page in pages),
        "total_findings": len(all_findings),
    }

    severities = {finding["severity"] for finding in all_findings}
    if "high" in severities:
        overall_status, severity = "fail", "high"
    elif "medium" in severities:
        overall_status, severity = "warning", "medium"
    elif "low" in severities:
        overall_status, severity = "warning", "low"
    else:
        overall_status, severity = "pass", "none"
    return all_findings, summary, overall_status, severity