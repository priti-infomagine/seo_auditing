"""
Score Calculator - Computes weighted SEO scores from rule results.

Industry-standard scoring aligned with Ahrefs/Semrush:
- Ahrefs: Only Errors (red) affect score = % pages without errors
- Semrush: Errors + Warnings affect score, weighted by severity and variety
- PromoPilot: Page-level weighting: Critical=1.0, Warning=0.4, Notice=0.1

Our approach: Category-weighted deduction model with severity-based penalties.
"""
from typing import Dict, List, Any, Optional
from app.modules.rule_engine.models.rule_result import RuleResult, Severity


class ScoreCalculator:
    """
    Calculates overall SEO score from rule results.

    Uses weighted categories aligned with industry focus areas:
    - Indexability/Crawlability: 25% (critical for visibility)
    - On-Page SEO: 20% (content optimization)
    - Technical SEO: 15% (foundation)
    - Content Quality: 15% (value to users)
    - Links/Internal Linking: 10% (crawl efficiency)
    - Performance: 5% (user experience)
    - Security/Trust: 5% (trust signals)
    - Structured Data: 3% (rich results)
    - Images/Media: 2% (optimization)

    Severity penalties (per failed check per page):
    - CRITICAL/ERROR: -8 points
    - HIGH/WARNING: -4 points
    - MEDIUM/INFO: -2 points
    - LOW/NOTICE: -1 point
    """

    # Category weights (sum = 1.0)
    DEFAULT_WEIGHTS = {
        "indexability": 0.25,    # Crawlability, noindex, canonical, robots
        "on_page": 0.20,         # Title, meta, headings, content structure
        "technical": 0.15,       # HTTPS, viewport, charset, doctype, redirects
        "content": 0.15,         # Word count, duplicates, freshness, structure
        "links": 0.10,           # Internal/external links, anchors, broken
        "performance": 0.05,     # Speed, TTFB, caching, compression
        "security": 0.05,        # Headers, SSL, mixed content
        "structured_data": 0.03, # Schema markup
        "images": 0.02,          # Alt, dimensions, formats, lazy loading
        "social": 0.00,          # Not scored (informational)
        "accessibility": 0.00,   # Not scored (separate audit)
    }

    # Map internal rule categories to scoring categories
    CATEGORY_MAP = {
        "indexability": "indexability",
        "technical": "technical",
        "on_page": "on_page",
        "content": "content",
        "links": "links",
        "performance": "performance",
        "security": "security",
        "schema": "structured_data",
        "images": "images",
        "social": "social",
        "accessibility": "accessibility",
        "url": "technical",
        "mobile": "technical",
        "http_status": "indexability",
        "hreflang": "indexability",
        "duplicate": "content",
        "perf": "performance",
        "core_web_vitals": "performance",
        "a11y": "accessibility",
    }

    # Severity penalties (per failed check) - aligned with Ahrefs/Semrush impact
    SEVERITY_PENALTIES = {
        Severity.CRITICAL: 20,   # Critical errors - major impact
        Severity.WARNING: 10,    # Warnings - significant impact
        Severity.INFO: 5,        # Notices - minor impact
        Severity.PASSED: 0,
        Severity.ERROR: 20,
    }

    def __init__(self, weights: Dict[str, float] = None, settings: Any = None):
        """
        Initialize calculator with custom weights.

        Args:
            weights: Custom category weights (defaults to DEFAULT_WEIGHTS)
            settings: Optional settings object with SEO_SCORER_WEIGHTS
        """
        if weights:
            self.weights = self._normalize_weights(weights)
        elif settings and getattr(settings, "SEO_SCORER_WEIGHTS", None):
            import json
            try:
                parsed = json.loads(settings.SEO_SCORER_WEIGHTS)
                self.weights = self._normalize_weights(parsed)
            except (json.JSONDecodeError, TypeError, ValueError):
                self.weights = self.DEFAULT_WEIGHTS
        else:
            self.weights = self.DEFAULT_WEIGHTS

    @staticmethod
    def _normalize_weights(weights: Dict[str, float]) -> Dict[str, float]:
        """Normalize weights to sum to 1.0."""
        total = sum(weights.values())
        if total > 0:
            return {k: v / total for k, v in weights.items()}
        return ScoreCalculator.DEFAULT_WEIGHTS

    def calculate_score(self, rule_results: List[RuleResult]) -> Dict[str, Any]:
        """
        Calculate overall SEO score from rule results.

        Args:
            rule_results: List of RuleResult objects from all rules

        Returns:
            Dictionary with overall score, breakdown, and statistics
        """
        # Group results by scoring category
        scoring_categories: Dict[str, List[RuleResult]] = {}
        for result in rule_results:
            cat = self.CATEGORY_MAP.get(result.category, result.category)
            if cat not in scoring_categories:
                scoring_categories[cat] = []
            scoring_categories[cat].append(result)

        # Calculate score for each scoring category
        category_scores = {}
        total_weighted_score = 0.0
        total_weight = 0.0

        for category, results in scoring_categories.items():
            cat_score = self._calculate_category_score(category, results)
            category_scores[category] = cat_score

            # Apply weight (skip zero-weight categories)
            weight = self.weights.get(category, 0.0)
            if weight > 0:
                total_weighted_score += cat_score["score"] * weight
                total_weight += weight

        # Normalize to 0-100
        if total_weight > 0:
            overall_score = min(100, max(0, total_weighted_score / total_weight))
        else:
            overall_score = 0.0

        # Count issues by severity
        critical_issues = sum(1 for r in rule_results if r.severity == Severity.CRITICAL and not r.passed)
        high_issues = sum(1 for r in rule_results if r.severity == Severity.WARNING and not r.passed)
        medium_issues = sum(1 for r in rule_results if r.severity == Severity.INFO and not r.passed)
        low_issues = sum(1 for r in rule_results if r.severity == Severity.PASSED and not r.passed)

        total_passed = sum(1 for r in rule_results if r.passed)
        total_failed = sum(1 for r in rule_results if not r.passed)

        return {
            "overall_score": round(overall_score, 1),
            "grade": self._get_grade(overall_score),
            "categories": category_scores,
            "total_rules": len(rule_results),
            "total_passed": total_passed,
            "total_failed": total_failed,
            "critical_issues": critical_issues,
            "high_issues": high_issues,
            "medium_issues": medium_issues,
            "low_issues": low_issues,
            "severity_breakdown": {
                "critical": critical_issues,
                "high": high_issues,
                "medium": medium_issues,
                "low": low_issues,
            }
        }

    def _calculate_category_score(self, category: str, results: List[RuleResult]) -> Dict[str, Any]:
        """Calculate score for a single category using deduction model."""
        if not results:
            return {
                "category": category,
                "score": 100.0,
                "max_score": 100.0,
                "weight": self.weights.get(category, 0.0),
                "rules_checked": 0,
                "rules_passed": 0,
                "rules_failed": 0,
                "issues_by_severity": {"critical": 0, "high": 0, "medium": 0, "low": 0},
            }

        # Start with 100 and deduct penalties
        score = 100.0
        issues = []
        warnings = []
        passed_rules = []
        issues_by_severity = {"critical": 0, "high": 0, "medium": 0, "low": 0}

        for result in results:
            if result.passed:
                passed_rules.append(result)
                # Small bonus for passing critical rules
                if result.severity == Severity.CRITICAL and result.score_impact > 0:
                    score += min(result.score_impact, 1)
            else:
                penalty = self.SEVERITY_PENALTIES.get(result.severity, 4)
                score -= penalty

                if result.severity == Severity.CRITICAL:
                    issues.append(result)
                    issues_by_severity["critical"] += 1
                elif result.severity == Severity.WARNING:
                    warnings.append(result)
                    issues_by_severity["high"] += 1
                elif result.severity == Severity.INFO:
                    warnings.append(result)
                    issues_by_severity["medium"] += 1
                else:
                    warnings.append(result)
                    issues_by_severity["low"] += 1

        # Clamp to 0-100
        score = min(100.0, max(0.0, score))

        return {
            "category": category,
            "score": round(score, 1),
            "max_score": 100.0,
            "weight": self.weights.get(category, 0.0),
            "rules_checked": len(results),
            "rules_passed": len(passed_rules),
            "rules_failed": len(issues) + len(warnings),
            "issues": issues,
            "warnings": warnings,
            "passed_rules": passed_rules,
            "issues_by_severity": issues_by_severity,
        }

    def _get_grade(self, score: float) -> str:
        """Convert SEO score to letter grade - stricter thresholds."""
        if score >= 95:
            return "A+"
        elif score >= 90:
            return "A"
        elif score >= 85:
            return "B+"
        elif score >= 80:
            return "B"
        elif score >= 75:
            return "C+"
        elif score >= 70:
            return "C"
        elif score >= 65:
            return "D+"
        elif score >= 60:
            return "D"
        elif score >= 50:
            return "E"
        else:
            return "F"


# ---------------------------------------------------------------------------
# Report-assembly configuration (category-first SEO audit report).
#
# These constants drive `app/modules/scorer/report_assembler.py`. They live here
# (in the scorer's weights/compute module) per project convention that scoring +
# report-structure config stays in one place, so report logic never hardcodes
# category order or status thresholds.
# ---------------------------------------------------------------------------

# Response-category order. `overall_summary` (order 1) is reserved as the report
# header and is never emitted as a real category. Remaining ids are sorted ascending
# when building the `categories` list.
CATEGORY_ORDER: Dict[str, int] = {
    "overall_summary": 1,
    "technical_seo": 2,
    "on_page_seo": 3,
    "content": 4,
    "off_page_seo": 5,
    "local_seo": 6,
    "geo_ai_readiness": 7,
    "headers": 8,
    "images": 9,
    "social": 10,
    "performance": 11,
    "security": 12,
    "accessibility": 13,
    "mobile": 14,
}

# Category status thresholds (minimum inclusive score per tier):
#   score >= good        -> "good"
#   score >= needs_attention -> "needs_attention"
#   otherwise           -> "critical"  (i.e. score >= critical)
STATUS_THRESHOLDS: Dict[str, float] = {
    "good": 70.0,
    "needs_attention": 50.0,
    "critical": 0.0,
}

# Source severity -> issue triage priority. Includes 'error' (rule-infra failures)
# so an unverified check is still triaged as high priority.
SEVERITY_PRIORITY_MAP: Dict[str, str] = {
    "critical": "high",
    "error": "high",
    "warning": "medium",
    "info": "low",
    "passed": "low",
}

# |score_impact| tiers -> estimated_impact. score_impact is negative (a penalty),
# so we compare its absolute value.
ESTIMATED_IMPACT_TIERS: Dict[str, float] = {
    "high": 10.0,
    "medium": 4.0,
}

# Real scorer internal category id -> report response category id.
# The engine uses short ids (on_page, technical, ...); the report uses friendly ids.
INTERNAL_TO_RESPONSE: Dict[str, str] = {
    "on_page": "on_page_seo",
    "technical": "technical_seo",
    "content": "content",
    "links": "off_page_seo",
    "images": "images",
    "schema": "technical_seo",
    "social": "social",
    "security": "security",
    "accessibility": "accessibility",
    "performance": "performance",
}

# Response category id -> site_categories for which the category is relevant.
# Absent key => relevant for every site_category. Drives reason_not_applicable.
# (e.g. local_business sites need Local SEO; ecommerce/blog sites do not.)
CATEGORY_SITE_APPLICABILITY: Dict[str, List[str]] = {
    "local_seo": ["local_business"],
    "geo_ai_readiness": ["blog", "news", "local_business", "portfolio", "ecommerce"],
}

# Response category id -> human-readable label.
CATEGORY_LABELS: Dict[str, str] = {
    "overall_summary": "Overall Summary",
    "technical_seo": "Technical SEO",
    "on_page_seo": "On-Page SEO",
    "content": "Content Quality",
    "off_page_seo": "Off-Page SEO",
    "local_seo": "Local SEO",
    "geo_ai_readiness": "Geo & AI Readiness",
    "headers": "Security Headers",
    "images": "Images & Media",
    "social": "Social Signals",
    "performance": "Performance",
    "security": "Security",
    "accessibility": "Accessibility",
    "mobile": "Mobile",
}


# ---------------------------------------------------------------------------
# Pass-rate scoring + status helper (consumed by audit_response_builder).
# ---------------------------------------------------------------------------

# Default pass threshold for a check: a check counts as "passed" only when 100%
# of pages pass it. Lower this to treat partial pass-through as passing.
PASS_THRESHOLD: float = 100.0

# Single source of truth for category status tiers (minimum inclusive score).
# Every category's `status` field must be derived from this table via get_status().
STATUS_THRESHOLDS_EXCELLENT: Dict[str, float] = {
    "excellent": 85.0,
    "good": 75.0,
    "needs_improvement": 60.0,
    "poor": 40.0,
    "critical": 0.0,
}


def get_status(score: Optional[float]) -> str:
    """Map a 0-100 score to a single status label.

    Standard SEO platform thresholds:
      90-100 -> excellent
      75-89  -> good
      60-74  -> needs_improvement
      40-59  -> poor
       0-39  -> critical

    One authoritative helper so no category-specific status override logic exists
    anywhere else in the codebase.
    """
    if score is None:
        return "not_available"
    try:
        score = float(score)
    except (TypeError, ValueError):
        return "not_available"
    if score >= STATUS_THRESHOLDS_EXCELLENT["excellent"]:
        return "excellent"
    if score >= STATUS_THRESHOLDS_EXCELLENT["good"]:
        return "good"
    if score >= STATUS_THRESHOLDS_EXCELLENT["needs_improvement"]:
        return "needs_improvement"
    if score >= STATUS_THRESHOLDS_EXCELLENT["poor"]:
        return "poor"
    return "critical"


# Category weights used by the pass-rate model (alias of ScoreCalculator.DEFAULT_WEIGHTS).
CATEGORY_WEIGHTS = ScoreCalculator.DEFAULT_WEIGHTS