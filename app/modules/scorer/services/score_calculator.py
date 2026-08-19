"""
Score Calculator - Computes weighted SEO scores from rule results.
"""
from typing import Dict, List, Any, Optional 
from app.modules.rule_engine.models.rule_result import RuleResult, CategoryScore, Severity


class ScoreCalculator:
    """
    Calculates overall SEO score from rule results.
    
    Uses weighted categories:
    - on_page: 20%
    - technical: 15%
    - content: 20%
    - links: 10%
    - images: 5%
    - schema: 5%
    - social: 5%
    - security: 10%
    - accessibility: 5%
    - performance: 5%
    
"""
    
    # Default category weights (can be customized)
    DEFAULT_WEIGHTS = {
        "on_page": 0.20,
        "technical": 0.15,
        "content": 0.20,
        "links": 0.10,
        "images": 0.05,
        "schema": 0.05,
        "social": 0.05,
        "security": 0.10,
        "accessibility": 0.05,
        "performance": 0.05,
        "performance": 0.05,
    }
    
    def __init__(self, weights: Dict[str, float] = None ):
        """
        Initialize calculator with custom weights.
        
        Args:
            weights: Custom category weights (defaults to DEFAULT_WEIGHTS)
        """
        self.weights = weights or self.DEFAULT_WEIGHTS
    
    def calculate_score(self, rule_results: List[RuleResult]) -> Dict[str, Any]:
        """
        Calculate overall SEO score from rule results.
        
        Args:
            rule_results: List of RuleResult objects from all rules
            
        Returns:
            Dictionary with overall score, breakdown, and statistics
        """
        # Group results by category
        categories: Dict[str, List[RuleResult]] = {}
        for result in rule_results:
            cat = result.category
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(result)
        
        # Calculate score for each category
        category_scores = {}
        total_weighted_score = 0.0
        total_weight = 0.0
        
        for category, results in categories.items():
            cat_score = self._calculate_category_score(category, results)
            category_scores[category] = cat_score
            
            # Apply weight
            weight = self.weights.get(category, 0.1)
            total_weighted_score += cat_score["score"] * weight
            total_weight += weight
        
        # Normalize to 0-100
        if total_weight > 0:
            overall_score = min(100, max(0, total_weighted_score / total_weight))
        else:
            overall_score = 0.0
        
        # Count issues
        critical_issues = sum(1 for r in rule_results if r.severity == Severity.CRITICAL and not r.passed)
        warnings = sum(1 for r in rule_results if r.severity == Severity.WARNING and not r.passed)
        total_passed = sum(1 for r in rule_results if r.passed)
        total_failed = sum(1 for r in rule_results if not r.passed)
        
        # Get top issues (sorted by score impact)
        top_issues = sorted(
            [r for r in rule_results if not r.passed],
            key=lambda r: r.score_impact
        )[:10]
        
        # Generate summary
        summary = self._generate_summary(
            overall_score,
            critical_issues,
            warnings,
            total_failed,
            total_passed
        )
        
        return {
            "overall_score": round(overall_score, 1),
            "grade": self._get_grade(overall_score),
            "categories": category_scores,
            "total_rules": len(rule_results),
            "total_passed": total_passed,
            "total_failed": total_failed,
            "critical_issues": critical_issues,
            "warnings": warnings,
            "summary": summary,
            "top_issues": top_issues,
        }
    
    def _calculate_category_score(self, category: str, results: List[RuleResult]) -> Dict[str, Any]:
        """Calculate score for a single category."""
        if not results:
            return {
                "category": category,
                "score": 100.0,
                "max_score": 100.0,
                "weight": self.weights.get(category, 0.1),
                "rules_checked": 0,
                "rules_passed": 0,
                "rules_failed": 0,
                "issues": [],
                "warnings": [],
                "passed_rules": [],
            }
        
        # Start with 100 and subtract impacts
        score = 100.0
        issues = []
        warnings = []
        passed_rules = []
        
        for result in results:
            if result.passed:
                passed_rules.append(result)
                # Bonus for passing
                if result.score_impact > 0:
                    score += result.score_impact
            else:
                if result.severity == Severity.CRITICAL:
                    issues.append(result)
                else:
                    warnings.append(result)
                
                # Penalty for failing
                score += result.score_impact  # score_impact is negative
        
        # Clamp to 0-100
        score = min(100.0, max(0.0, score))
        
        return {
            "category": category,
            "score": round(score, 1),
            "max_score": 100.0,
            "weight": self.weights.get(category, 0.1),
            "rules_checked": len(results),
            "rules_passed": len(passed_rules),
            "rules_failed": len(issues) + len(warnings),
            "issues": issues,
            "warnings": warnings,
            "passed_rules": passed_rules,
        }
    
    def _get_grade(self, score: float) -> str:
        """Convert SEO score to letter grade."""
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
        elif score >= 60:
            return "D"
        elif score >= 50:
            return "E"
        else:
            return "F"
    
    def _generate_summary(
        self,
        score: float,
        critical: int,
        warnings: int,
        failed: int,
        passed: int
    ) -> str:
        """Generate human-readable summary."""
        grade = self._get_grade(score)
        
        if score >= 90:
            summary = f"Excellent! Your site scores {score:.1f}/100 (Grade {grade}). "
            summary += "Your website follows SEO best practices."
        elif score >= 80:
            summary = f"Good! Your site scores {score:.1f}/100 (Grade {grade}). "
            summary += "Minor improvements recommended."
        elif score >= 70:
            summary = f"Fair. Your site scores {score:.1f}/100 (Grade {grade}). "
            summary += f"{warnings} warnings and {critical} critical issues need attention."
        elif score >= 60:
            summary = f"Poor. Your site scores {score:.1f}/100 (Grade {grade}). "
            summary += f"Significant improvements needed ({critical} critical issues)."
        else:
            summary = f"Critical. Your site scores {score:.1f}/100 (Grade {grade}). "
            summary += "Major SEO issues require immediate attention."

        return summary


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
    "good": 80.0,
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
    "excellent": 90.0,
    "good": 80.0,
    "poor": 60.0,
    "critical": 0.0,
}


def get_status(score: Optional[float]) -> str:
    """Map a 0-100 score to a single status label (excellent/good/poor/critical).

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
    if score >= STATUS_THRESHOLDS_EXCELLENT["poor"]:
        return "poor"
    return "critical"


# Category weights used by the pass-rate model (alias of ScoreCalculator.DEFAULT_WEIGHTS).
CATEGORY_WEIGHTS = ScoreCalculator.DEFAULT_WEIGHTS