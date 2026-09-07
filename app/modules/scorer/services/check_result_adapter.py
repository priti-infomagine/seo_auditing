"""
Check Result Adapter - bridges the existing ScorerService/ScoreCalculator output into the
report assembler's `CheckResult` contract.

This is the ONLY module that understands the `ScorerService`/`ScoreCalculator` output shapes;
the report assembler itself stays decoupled from scorer internals. It is pure (no DB, network,
or LLM) and lives in-scope under `app/modules/scorer/`.

It does NOT change how `compute.py` (ScoreCalculator) calculates scores: it reads the
precomputed `category_score`/`weight` and the `overall_score`/`grade` straight off the
scorer output and passes them through to the report layer untouched. It only flattens the
per-category `issues`/`warnings`/`passed_rules` buckets into a single list of per-check,
per-page `CheckResult` items.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Union

from app.schemas.report_schemas import CheckResult
from app.modules.rule_engine.models.rule_result import RuleResult
from app.modules.scorer.services.score_calculator import (
    CATEGORY_SITE_APPLICABILITY,
    INTERNAL_TO_RESPONSE,
)

NumberRe = re.compile(r"-?\d+(?:\.\d+)?")


def _resolve_response_category(internal_category: str) -> str:
    """Internal scorer category id -> report response category id."""
    return INTERNAL_TO_RESPONSE.get(internal_category, internal_category)


def _is_relevant(response_category_id: str, site_category: str) -> bool:
    """True when a report category applies to this site_category (drives applicability)."""
    allowed = CATEGORY_SITE_APPLICABILITY.get(response_category_id)
    return True if allowed is None else (site_category in allowed)


def _to_dict(result: Union[RuleResult, Dict[str, Any]]) -> Dict[str, Any]:
    """Normalize a RuleResult (pydantic) or a plain dict into a plain-dict view."""
    if isinstance(result, RuleResult):
        sev = result.severity
        sev_val = sev.value if hasattr(sev, "value") else str(sev)
        return {
            "rule_id": result.rule_id,
            "name": result.name,
            "category": result.category,
            "severity": sev_val,
            "passed": bool(result.passed),
            "score_impact": float(result.score_impact or 0.0),
            "message": result.message or "",
            "recommendation": result.recommendation,
            "data": result.data,
            "tags": result.tags,
        }
    return dict(result) if isinstance(result, dict) else {}


def _per_check_score(passed: bool, score_impact: float) -> float:
    """Translate pass/fail + the already-decided penalty into a 0-100 check figure.

    This is a reshape (not a recompute): ScoreCalculator already decided pass/fail and the
    penalty magnitude. We only map that penalty onto a 0-100 scale for weighted aggregation.
    """
    if passed:
        return 100.0
    return max(0.0, min(100.0, 100.0 + score_impact))


def _extract_found_value(message: str) -> Optional[Any]:
    """Best-effort synthesis of a concrete `found_value` from the rule message.

    Many rules leave `data=None`; this extracts the leading numeric fact so every issue
    still surfaces *something found*. Rules that fill structured `data` are far richer and
    take precedence (the assembler uses `evidence=data`).
    """
    if not message:
        return None
    nums = NumberRe.findall(message)
    if nums:
        return nums[0]
    return message.strip()[:80]


def _normalize_severity(severity: str, passed: bool) -> str:
    """Source severity -> CheckResult severity. Passed checks become 'passed'."""
    if passed:
        return "passed"
    return (severity or "info").lower()


def build_check_results(
    scorer_output: Dict[str, Any],
    page_url: str,
    site_category: str,
    rule_weights: Optional[Dict[str, float]] = None,
) -> List[CheckResult]:
    """Convert a single page's ScorerService/ScoreCalculator output into CheckResult items.

    Args:
        scorer_output: dict from `ScoreCalculator.calculate_score` (which also carries the
            per-category `issues`/`warnings`/`passed_rules` lists) — optionally enriched with
            the `rule_results` key that `ScorerService.score_parsed_data` attaches.
        page_url: URL of the page this score was computed for (the offending page).
        site_category: business type driving per-category applicability/reasons.
        rule_weights: optional `rule_id -> weight` map (from `BaseRule.weight`). Defaults to 1.0.

    Returns:
        One `CheckResult` per rule result, carrying the precomputed category score and the
        overall score through for pass-through by the assembler.
    """
    rule_weights = rule_weights or {}
    overall_value = scorer_output.get("overall_score")
    overall_grade = scorer_output.get("grade")
    categories = scorer_output.get("categories", {}) or {}

    out: List[CheckResult] = []
    for cat_id, cat in categories.items():
        cat_view = cat if isinstance(cat, dict) else {}
        cat_score = cat_view.get("score")
        cat_grade = cat_view.get("grade")
        # ScoreCalculator buckets: issues (critical failures), warnings (warn/info failures),
        # passed_rules (clean). issues+warnings are failed; passed_rules are clean.
        for bucket_name, is_passed in (
            ("issues", False),
            ("warnings", False),
            ("passed_rules", True),
        ):
            for raw in cat_view.get(bucket_name, []) or []:
                r = _to_dict(raw)
                response_cat = _resolve_response_category(cat_id)
                score_impact = float(r.get("score_impact", 0.0))
                evidence = r.get("data") or {}
                found = evidence.get("found_value")
                if found is None:
                    found = _extract_found_value(r.get("message", ""))
                out.append(
                    CheckResult(
                        check_id=r.get("rule_id", ""),
                        category=cat_id,
                        weight=float(rule_weights.get(r.get("rule_id", ""), 1.0)),
                        applicable=_is_relevant(response_cat, site_category),
                        passed=is_passed,
                        severity=_normalize_severity(r.get("severity", ""), is_passed),
                        score_impact=score_impact,
                        score=_per_check_score(is_passed, score_impact),
                        category_score=cat_score,
                        category_grade=cat_grade,
                        overall_value=overall_value,
                        overall_grade=overall_grade,
                        page_url=page_url,
                        title=r.get("name", r.get("rule_id", "")),
                        description=(r.get("message") or None),
                        recommendation=r.get("recommendation"),
                        found_value=found,
                        expected_value=evidence.get("expected_value"),
                        evidence=(evidence or None),
                    )
                )
    return out
