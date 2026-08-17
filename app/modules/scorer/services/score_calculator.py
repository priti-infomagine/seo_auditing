"""
Score Calculator - Computes weighted SEO scores from rule results.
"""
from typing import Dict, List, Any 
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
    
    def __init__(self, weights: Dict[str, float] ):
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