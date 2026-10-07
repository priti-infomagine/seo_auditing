"""Analysis and evaluation of redirect check results.

Classifies each URL's redirect chain into findings (issues/opportunities),
produces a summary, and computes an overall status + severity.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .constants import RECOMMENDATION_CATALOG
from .schema import (
    RedirectFinding,
    RedirectRecommendation,
    RedirectSummary,
    RedirectUrlResult,
)


@dataclass
class AnalysisOutcome:
    """Result of evaluating all redirect URL results for a domain."""

    findings: list[RedirectFinding] = field(default_factory=list)
    recommendations: list[RedirectRecommendation] = field(default_factory=list)
    summary: RedirectSummary = field(default_factory=RedirectSummary)
    overall_status: str = "pass"
    severity: str = "none"

    def _deduplicate_recommendations(self) -> None:
        seen_codes: set[str] = set()
        deduped: list[RedirectRecommendation] = []
        for rec in self.recommendations:
            if rec.code not in seen_codes:
                seen_codes.add(rec.code)
                deduped.append(rec)
        self.recommendations = deduped

    def _compute_overall_status(self) -> None:
        has_fail = any(f.status == "fail" for f in self.findings)
        has_warning = any(f.status == "warning" for f in self.findings)
        has_medium = any(f.severity == "medium" for f in self.findings)
        has_high = any(f.severity == "high" for f in self.findings)

        if has_fail or has_high:
            self.overall_status = "fail"
            self.severity = "high" if has_high else "medium"
        elif has_warning or has_medium:
            self.overall_status = "warning"
            self.severity = "medium" if has_medium else "low"
        else:
            self.overall_status = "pass"
            self.severity = "none"


class RedirectCheckAnalyzer:
    """Analyzes redirect check results to produce findings and summary."""

    MAX_REDIRECT_HOPS_WARN = 2

    @classmethod
    def analyze(
        cls,
        results: list[RedirectUrlResult],
        domain: str,
    ) -> AnalysisOutcome:
        """Evaluate a list of redirect URL results.

        Args:
            results: All ``RedirectUrlResult`` objects for the domain.
            domain: The normalized domain host for internal/external classification.

        Returns:
            ``AnalysisOutcome`` with findings, recommendations, summary,
            overall status, and severity.
        """
        outcome = AnalysisOutcome()
        outcome.summary = RedirectSummary()

        by_status_class: dict[str, int] = {"ok": 0, "redirect": 0, "broken": 0, "unverified": 0}

        for result in results:
            cls._classify_result(result, domain, outcome, by_status_class)

        outcome.summary.by_status_class = by_status_class

        for finding in outcome.findings:
            rec_data = RECOMMENDATION_CATALOG.get(finding.code)
            if rec_data:
                outcome.recommendations.append(
                    RedirectRecommendation(
                        code=finding.code,
                        priority=rec_data["priority"],
                        title=rec_data["title"],
                        message=rec_data.get("message", f"Fix {finding.code}"),
                        fix=rec_data.get("fix", "See recommendation details"),
                        where_to_fix=rec_data["where_to_fix"],
                        evidence=finding.evidence,
                    )
                )

        outcome._deduplicate_recommendations()
        outcome._compute_overall_status()
        return outcome

    @classmethod
    def _classify_result(
        cls,
        result: RedirectUrlResult,
        domain: str,
        outcome: AnalysisOutcome,
        by_status_class: dict[str, int],
    ) -> None:
        url = result.url
        summary = outcome.summary
        summary.total_urls += 1

        if result.error or result.final_status is None:
            summary.broken += 1
            by_status_class["unverified"] += 1
            outcome.findings.append(
                RedirectFinding(
                    code="broken_link",
                    severity="high",
                    status="fail",
                    message=f"Redirect check failed for {url}",
                    evidence=result.error or "No response received",
                    target_url=url,
                    redirect_count=result.redirect_count,
                    final_status=result.final_status,
                )
            )
            return

        status = result.final_status or 0

        if 200 <= status < 300:
            by_status_class["ok"] += 1
            if not result.is_redirect:
                return
        elif 300 <= status < 400:
            by_status_class["redirect"] += 1
        elif status >= 400:
            summary.broken += 1
            by_status_class["broken"] += 1
            outcome.findings.append(
                RedirectFinding(
                    code="broken_link",
                    severity="high",
                    status="fail",
                    message=f"Final destination for {url} returned HTTP {status}",
                    evidence=f"{url} -> {result.final_url} (HTTP {status})",
                    target_url=url,
                    redirect_count=result.redirect_count,
                    final_status=status,
                )
            )
            return
        else:
            by_status_class["unverified"] += 1
            return

        if result.is_redirect:
            summary.redirects_found += 1

            if result.redirect_count > 0:
                summary.redirect_chains += 1

            if result.redirect_count > cls.MAX_REDIRECT_HOPS_WARN:
                outcome.findings.append(
                    RedirectFinding(
                        code="redirect_chain_long",
                        severity="medium",
                        status="warning",
                        message=f"Long redirect chain for {url} ({result.redirect_count} hops)",
                        evidence=f"{url} has {result.redirect_count} redirect hops (recommend ≤ 2)",
                        target_url=url,
                        redirect_count=result.redirect_count,
                        final_status=status,
                    )
                )

            if result.is_internal_redirect:
                summary.internal_redirects += 1
                outcome.findings.append(
                    RedirectFinding(
                        code="redirect_internal",
                        severity="low",
                        status="warning",
                        message=f"Internal redirect for {url}",
                        evidence=f"{url} redirects to {result.final_url}",
                        target_url=url,
                        redirect_count=result.redirect_count,
                        final_status=status,
                    )
                )

            if result.is_external_redirect:
                summary.external_redirects += 1
                outcome.findings.append(
                    RedirectFinding(
                        code="redirect_external",
                        severity="low",
                        status="warning",
                        message=f"External redirect for {url}",
                        evidence=f"{url} redirects to {result.final_url}",
                        target_url=url,
                        redirect_count=result.redirect_count,
                        final_status=status,
                    )
                )

            if result.error == "Redirect loop detected." or "loop" in (result.error or "").lower():
                summary.loops += 1
                outcome.findings.append(
                    RedirectFinding(
                        code="redirect_loop",
                        severity="high",
                        status="fail",
                        message=f"Redirect loop detected for {url}",
                        evidence=result.error,
                        target_url=url,
                        redirect_count=result.redirect_count,
                        final_status=status,
                    )
                )

            if result.meta_refresh:
                summary.meta_refresh += 1
                outcome.findings.append(
                    RedirectFinding(
                        code="meta_refresh_redirect",
                        severity="low",
                        status="warning",
                        message=f"Meta refresh redirect found for {url}",
                        evidence=f"meta_refresh content: {result.meta_refresh}",
                        target_url=url,
                        redirect_count=result.redirect_count,
                        final_status=status,
                    )
                )

            if cls._is_insecure_redirect(url, result.final_url):
                summary.insecure += 1
                outcome.findings.append(
                    RedirectFinding(
                        code="insecure_redirect",
                        severity="medium",
                        status="warning",
                        message=f"Insecure redirect for {url} (HTTP → HTTPS mismatch)",
                        evidence=f"{url} starts with HTTP, final destination is HTTPS",
                        target_url=url,
                        redirect_count=result.redirect_count,
                        final_status=status,
                    )
                )

    @staticmethod
    def _is_insecure_redirect(original_url: str, final_url: str | None) -> bool:
        """Detect HTTPS→HTTP redirects (downgrade from secure to insecure)."""
        if not final_url:
            return False
        try:
            from urllib.parse import urlparse

            orig_scheme = urlparse(original_url).scheme.lower()
            final_scheme = urlparse(final_url).scheme.lower()
            return orig_scheme == "https" and final_scheme == "http"
        except Exception:
            return False
