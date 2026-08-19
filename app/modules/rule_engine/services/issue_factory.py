"""
RuleResult → SEOIssue converter (the single normalization boundary).

The rule engine emits RuleResult objects (one per rule per page). This module is the
ONLY place that turns a RuleResult into a standardized SEOIssue, so every rule's output
flows through one canonical shape.

The crawler/parser already supplied the underlying evidence (captured in RuleData by the
individual rules from parsed_page_facts / page_seo_data / page_network_data). The converter
does NOT scrape or parse HTML — it reshapes what the rules already produced.
"""
from __future__ import annotations

import logging
from typing import Optional

from app.modules.rule_engine.models.rule_evidence_map import (
    RULE_AFFECTED_PART,
    HIGH_IMPACT_WARNINGS,
    RULE_TITLES,
)
from app.modules.rule_engine.models.rule_result import RuleResult, Severity
from app.modules.rule_engine.models.seo_issue import SEOIssue, SeverityTier

logger = logging.getLogger(__name__)

# Rules whose WARNING should NOT be promoted to high (explicit negative set is the
# HIGH_IMPACT_WARNINGS positive set; everything else default applies).


class RuleResultToSEOIssueConverter:
    """Convert a legacy RuleResult into a standardized SEOIssue."""

    @staticmethod
    def severity_tier(result: RuleResult) -> SeverityTier:
        """
        Map the existing Severity enum to the 4-tier model WITHOUT using
        score_impact (spec §3). CRITICAL/WARNING are split using the explicit
        HIGH_IMPACT_WARNINGS registry for the WARNING→high promotion.
        """
        if result.severity == Severity.CRITICAL:
            return SeverityTier.CRITICAL
        if result.severity == Severity.WARNING:
            return SeverityTier.HIGH if result.rule_id in HIGH_IMPACT_WARNINGS else SeverityTier.MEDIUM
        if result.severity == Severity.INFO:
            return SeverityTier.LOW
        # PASSED / ERROR fall back to LOW (passed results are never counted as issues)
        return SeverityTier.LOW

    @staticmethod
    def affected_part(rule_id: str) -> str:
        """Resolve the affected_part from the registry; 'unknown' + log if missing."""
        part = RULE_AFFECTED_PART.get(rule_id)
        if part is None:
            logger.warning(
                "rule_evidence_map: rule_id %r has no affected_part mapping; "
                "using 'unknown'. Add it to RULE_AFFECTED_PART.", rule_id
            )
            return "unknown"
        return part

    @staticmethod
    def rule_title(rule_id: str) -> str:
        return RULE_TITLES.get(rule_id, rule_id)

    @classmethod
    def from_rule_result(
        cls,
        result: RuleResult,
        page_url: str,
        page_id: Optional[str] = None,
        crawl_id: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> Optional[SEOIssue]:
        """
        Convert a RuleResult into a SEOIssue.

        Returns None for synthetic ERROR results — those are routed to `errors[]`
        by the response builder, not to `issues[]`.
        """
        if result.severity == Severity.ERROR:
            return None

        return SEOIssue(
            rule_id=result.rule_id,
            severity=cls.severity_tier(result),
            category=result.category,
            status="passed" if result.passed else "failed",
            page_url=page_url,
            affected_part=cls.affected_part(result.rule_id),
            evidence=_minify_evidence(result.data),
            score_impact=result.score_impact,
            message=result.message if isinstance(result.message, str) else None,
            recommendation=result.recommendation if isinstance(result.recommendation, str) else None,
            page_id=page_id,
            crawl_id=crawl_id,
            project_id=project_id,
        )


def _minify_evidence(data) -> dict:
    """
    Keep evidence factual and compact. The rule's `data` field already holds the
    minimal facts it chose to record. We just ensure it is a JSON-safe dict.
    """
    if isinstance(data, dict):
        return data
    if data is None:
        return {}
    return {"value": data}
