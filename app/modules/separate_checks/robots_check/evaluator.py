"""
Robots.txt evaluation logic.

Pure-CPU evaluation: takes the parsed robots.txt structure + fetch result +
sitemap reachability data and produces a list of findings with severity
and an aggregated overall status.
"""
from typing import Optional

from app.core.logger import logger

from .fetcher import Evaluation, FetchResult, ParsedRobots
from .model import OverallStatus, Severity, FetchStatus

MAX_ROBOTS_SIZE_BYTES = 500_000

ASSET_PATH_PATTERNS = (
    "/css/",
    "/js/",
    "/static/",
    "*.css",
    "*.js",
)


def evaluate(
    parsed: Optional[ParsedRobots],
    fetch_result: FetchResult,
    sitemap_reachability: Optional[list[dict]] = None,
) -> Evaluation:
    """Evaluate parsed robots.txt data into findings.

    Each evaluation rule is wrapped in its own try-except so a failure in
    one rule never prevents the others from running.
    """
    findings: list[dict] = []
    sitemap_reachability = sitemap_reachability or []

    blocks_entire_site = False
    blocks_assets = False
    oversized = False

    # ── Rule: no robots.txt ──────────────────────────────────────────────
    try:
        if fetch_result.fetch_status == FetchStatus.NOT_FOUND:
            findings.append({
                "code": "robots_missing",
                "severity": Severity.MEDIUM.value,
                "status": OverallStatus.FAIL.value,
                "message": "robots.txt not found (HTTP 404). Create a robots.txt at the site root.",
                "evidence": "HTTP 404 on /robots.txt",
            })
        elif fetch_result.fetch_status == FetchStatus.UNREACHABLE:
            findings.append({
                "code": "robots_unreachable",
                "severity": Severity.MEDIUM.value,
                "status": OverallStatus.WARNING.value,
                "message": "robots.txt could not be fetched. Site may be blocking crawlers.",
                "evidence": f"Fetch error: {fetch_result.error or 'unknown'}",
            })
    except Exception as exc:
        logger.warning("evaluate: robots_missing rule failed: %s", exc)

    # Early exit: if we have no parsed data, the missing/unreachable rule
    # above covers it; return NOT_APPLICABLE.
    if parsed is None or fetch_result.fetch_status != FetchStatus.SUCCESS:
        if not findings:
            findings.append({
                "code": "robots_unavailable",
                "severity": Severity.LOW.value,
                "status": OverallStatus.NOT_APPLICABLE.value,
                "message": "robots.txt could not be retrieved or parsed.",
                "evidence": "No parsed data available",
            })
        return _finalize(
            findings, OverallStatus.NOT_APPLICABLE.value,
            Severity.LOW.value, False, False, False,
            "robots.txt not available or unreachable",
        )

    # ── Rule: site-wide block ────────────────────────────────────────────
    try:
        for group in parsed.user_agent_groups:
            uas = group.get("user_agents", [])
            disallow = group.get("disallow", [])
            if "*" in uas or any("*" in ua for ua in uas):
                for path in disallow:
                    if path == "/" or path == "/*":
                        blocks_entire_site = True
                        findings.append({
                            "code": "robots_site_block",
                            "severity": Severity.CRITICAL.value,
                            "status": OverallStatus.FAIL.value,
                            "message": "Wildcard user-agent group disallows all paths (Disallow: /), blocking search engine indexing.",
                            "evidence": f"Disallow: {path} in group {uas}",
                        })
                        break
                if blocks_entire_site:
                    break
    except Exception as exc:
        logger.warning("evaluate: robots_site_block rule failed: %s", exc)

    # ── Rule: asset blocking ─────────────────────────────────────────────
    try:
        for group in parsed.user_agent_groups:
            uas = group.get("user_agents", [])
            disallow = group.get("disallow", [])
            for path in disallow:
                for pattern in ASSET_PATH_PATTERNS:
                    if path == pattern or path.startswith(pattern):
                        blocks_assets = True
                        findings.append({
                            "code": "robots_asset_block",
                            "severity": Severity.HIGH.value,
                            "status": OverallStatus.FAIL.value,
                            "message": f"Rules block static assets: Disallow: {path}. Search engines need CSS/JS to render and index pages.",
                            "evidence": f"Disallow: {path} in group {uas}",
                        })
                        break
                if blocks_assets:
                    break
            if blocks_assets:
                break
    except Exception as exc:
        logger.warning("evaluate: robots_asset_block rule failed: %s", exc)

    # ── Rule: sitemap declared ───────────────────────────────────────────
    try:
        if not parsed.sitemaps:
            findings.append({
                "code": "robots_sitemap_declared",
                "severity": Severity.LOW.value,
                "status": OverallStatus.WARNING.value,
                "message": "No Sitemap directive found in robots.txt. Search engines may miss pages.",
                "evidence": "No sitemap URLs declared",
            })
    except Exception as exc:
        logger.warning("evaluate: robots_sitemap_declared rule failed: %s", exc)

    # ── Rule: sitemap reachable ──────────────────────────────────────────
    try:
        if parsed.sitemaps and sitemap_reachability:
            for entry in sitemap_reachability:
                if not entry.get("reachable", False):
                    findings.append({
                        "code": "robots_sitemap_reachable",
                        "severity": Severity.MEDIUM.value,
                        "status": OverallStatus.WARNING.value,
                        "message": f"Sitemap URL is not reachable: {entry.get('url', 'unknown')}",
                        "evidence": f"HTTP {entry.get('status_code', 0)}: {entry.get('error', 'unreachable')}",
                    })
    except Exception as exc:
        logger.warning("evaluate: robots_sitemap_reachable rule failed: %s", exc)

    # ── Rule: syntax warnings ────────────────────────────────────────────
    try:
        if parsed.syntax_warnings:
            findings.append({
                "code": "robots_syntax",
                "severity": Severity.LOW.value,
                "status": OverallStatus.WARNING.value,
                "message": f"Syntax issues detected in robots.txt: {'; '.join(parsed.syntax_warnings)}",
                "evidence": f"{len(parsed.syntax_warnings)} warning(s)",
            })
    except Exception as exc:
        logger.warning("evaluate: robots_syntax rule failed: %s", exc)

    # ── Rule: oversized ──────────────────────────────────────────────────
    try:
        if fetch_result.content_length > MAX_ROBOTS_SIZE_BYTES:
            oversized = True
            findings.append({
                "code": "robots_oversized",
                "severity": Severity.LOW.value,
                "status": OverallStatus.WARNING.value,
                "message": f"robots.txt is {fetch_result.content_length} bytes (> {MAX_ROBOTS_SIZE_BYTES}). Search engines may truncate parsing at 500 KB.",
                "evidence": f"Content-Length: {fetch_result.content_length}",
            })
    except Exception as exc:
        logger.warning("evaluate: robots_oversized rule failed: %s", exc)

    # ── Rule: oversized via raw text length ──────────────────────────────
    try:
        if (
            not oversized
            and fetch_result.text
            and len(fetch_result.text) > MAX_ROBOTS_SIZE_BYTES
        ):
            oversized = True
            findings.append({
                "code": "robots_oversized",
                "severity": Severity.LOW.value,
                "status": OverallStatus.WARNING.value,
                "message": f"robots.txt is {len(fetch_result.text)} bytes (> {MAX_ROBOTS_SIZE_BYTES}). Search engines may truncate parsing at 500 KB.",
                "evidence": f"Text length: {len(fetch_result.text)}",
            })
    except Exception as exc:
        logger.warning("evaluate: robots_oversized (text) rule failed: %s", exc)

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

    return _finalize(
        findings, max_status, max_severity,
        blocks_entire_site, blocks_assets, oversized,
        evidence_str,
    )


def _finalize(
    findings: list[dict],
    overall_status: str,
    severity: str,
    blocks_entire_site: bool,
    blocks_assets: bool,
    oversized: bool,
    evidence_str: Optional[str],
) -> Evaluation:
    """Build the final Evaluation, defaulting to PASS when no findings."""
    if not findings and overall_status == "not_applicable":
        overall_status = OverallStatus.PASS.value
        severity = Severity.NONE.value

    if not findings:
        findings.append({
            "code": "robots_ok",
            "severity": Severity.NONE.value,
            "status": OverallStatus.PASS.value,
            "message": "robots.txt is well-formed and does not block crawlers.",
            "evidence": "All checks passed",
        })
        overall_status = OverallStatus.PASS.value
        severity = Severity.NONE.value

    return Evaluation(
        findings=findings,
        overall_status=overall_status,
        severity=severity,
        blocks_entire_site=blocks_entire_site,
        blocks_assets=blocks_assets,
        oversized=oversized,
        evidence_str=evidence_str,
    )
