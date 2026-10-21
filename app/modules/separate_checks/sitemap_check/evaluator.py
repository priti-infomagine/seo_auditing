"""
Sitemap check evaluation logic.

Pure-CPU evaluation: takes the robots.txt fetch result, declared sitemaps,
and per-file sitemap results, producing findings with severity and an
aggregated overall status.

Mirrors the rule-wrapping pattern of ``robots_check.evaluator.evaluate``.
"""
from dataclasses import dataclass, field
from typing import Optional

from app.core.logger import logger

from .model import FetchStatus, OverallStatus, Severity

MAX_TOTAL_SITEMAPS = 50


@dataclass(slots=True)
class Evaluation:
    """Structured evaluation result from the evaluator."""

    findings: list[dict] = field(default_factory=list)
    overall_status: str = "not_applicable"
    severity: str = "none"
    evidence_str: Optional[str] = None


def _finalize(
    findings: list[dict],
    overall_status: str,
    severity: str,
    evidence: Optional[str],
) -> Evaluation:
    """Create the final :class:`Evaluation` from computed values."""
    return Evaluation(
        findings=findings,
        overall_status=overall_status,
        severity=severity,
        evidence_str=evidence,
    )


def evaluate(
    robots_fetch_status: FetchStatus,
    sitemaps_declared: list[str],
    sitemap_results: list[dict],
) -> Evaluation:
    """Evaluate sitemap discovery results into findings.

    Each evaluation rule is wrapped in its own try-except so a failure in
    one rule never prevents the others from running.
    """
    findings: list[dict] = []
    sitemap_results = sitemap_results or []

    # ── Rule: no sitemaps at all ──────────────────────────────────────
    try:
        if not sitemap_results:
            findings.append({
                "code": "sitemap_none_found",
                "severity": Severity.MEDIUM.value,
                "status": OverallStatus.WARNING.value,
                "message": "No sitemap files were found. Declare sitemaps in "
                "robots.txt (Sitemap: directive) or place them at "
                "/sitemap.xml or /sitemap_index.xml.",
                "evidence": (
                    f"robots.txt fetch status: {robots_fetch_status.value}; "
                    f"declared sitemaps: {len(sitemaps_declared)}; "
                    f"discovered files: 0"
                ),
            })
    except Exception as exc:
        logger.warning("evaluate: sitemap_none_found rule failed: %s", exc)

    # ── Rule: unreachable / non-200 sitemaps ────────────────────────────
    try:
        for result in sitemap_results:
            status_code = result.get("status_code", 0)
            error = result.get("error")
            if status_code == 0 or not (200 <= status_code < 400):
                findings.append({
                    "code": "sitemap_unreachable",
                    "severity": Severity.MEDIUM.value,
                    "status": OverallStatus.WARNING.value,
                    "message": (
                        f"Sitemap at {result.get('url', 'unknown')} is not "
                        f"reachable (HTTP {status_code})."
                    ),
                    "evidence": f"HTTP {status_code}: {error or 'unreachable'}",
                })
    except Exception as exc:
        logger.warning("evaluate: sitemap_unreachable rule failed: %s", exc)

    # ── Rule: redirect detection ───────────────────────────────────────
    try:
        redirects: list[str] = []
        for result in sitemap_results:
            url = result.get("url", "")
            final_url = result.get("final_url", "")
            if url and final_url and url != final_url:
                redirects.append(
                    f"{url} -> {final_url}"
                )
        if redirects:
            findings.append({
                "code": "sitemap_redirect_detected",
                "severity": Severity.LOW.value,
                "status": OverallStatus.WARNING.value,
                "message": (
                    f"{len(redirects)} sitemap(s) redirect to a different URL. "
                    f"The redirect is recorded so crawlers know where the "
                    f"sitemap actually lives."
                ),
                "evidence": "; ".join(redirects),
            })
    except Exception as exc:
        logger.warning("evaluate: sitemap_redirect_detected rule failed: %s", exc)

    # ── Rule: sitemap index with no children ──────────────────────────
    try:
        for result in sitemap_results:
            if result.get("is_index") and result.get("entry_count", 0) == 0:
                findings.append({
                    "code": "sitemap_index_empty",
                    "severity": Severity.LOW.value,
                    "status": OverallStatus.WARNING.value,
                    "message": (
                        f"Sitemap index at {result.get('url', 'unknown')} "
                        f"did not contain any child <sitemap> entries."
                    ),
                    "evidence": "Zero child sitemap URLs in index",
                })
    except Exception as exc:
        logger.warning("evaluate: sitemap_index_empty rule failed: %s", exc)

    # ── Rule: content-type check ───────────────────────────────────────
    try:
        xml_content_types = {
            "application/xml",
            "text/xml",
            "application/rss+xml",
        }
        for result in sitemap_results:
            if (
                result.get("status_code", 0) >= 200
                and result.get("status_code", 0) < 400
                and result.get("entry_count", 0) > 0
            ):
                ct = (result.get("content_type") or "").lower()
                if ct and ct not in xml_content_types:
                    findings.append({
                        "code": "sitemap_wrong_content_type",
                        "severity": Severity.LOW.value,
                        "status": OverallStatus.WARNING.value,
                        "message": (
                            f"Sitemap at {result.get('url', 'unknown')} "
                            f"serves Content-Type '{ct}' instead of an "
                            f"XML type. Search engines may not parse it."
                        ),
                        "evidence": f"Content-Type: {ct}",
                    })
    except Exception as exc:
        logger.warning("evaluate: sitemap_wrong_content_type rule failed: %s", exc)

    # ── Determine overall status and severity ────────────────────────────
    severity_order = {"critical": 5, "high": 4, "medium": 3, "low": 2, "none": 1}
    status_order = {"fail": 4, "warning": 3, "pass": 2, "not_applicable": 1}

    max_severity = "none"
    max_status = "pass"
    evidence_parts: list[str] = []

    for f in findings:
        sev = f.get("severity", "none")
        st = f.get("status", "pass")
        if severity_order.get(sev, 0) > severity_order.get(max_severity, 0):
            max_severity = sev
        if status_order.get(st, 0) > status_order.get(max_status, 0):
            max_status = st
        evidence_parts.append(f"{f['code']}: {f['status']}")

    evidence_str = "; ".join(evidence_parts) if evidence_parts else None

    if not findings:
        findings.append({
            "code": "sitemap_ok",
            "severity": Severity.NONE.value,
            "status": OverallStatus.PASS.value,
            "message": (
                f"Sitemap check passed: {len(sitemap_results)} sitemap file(s) "
                f"verified."
            ),
            "evidence": "All sitemaps reachable and properly configured",
        })
        max_severity = Severity.NONE.value
        max_status = OverallStatus.PASS.value

    if max_status == "pass":
        max_severity = Severity.NONE.value

    return _finalize(
        findings,
        max_status,
        max_severity,
        evidence_str,
    )
