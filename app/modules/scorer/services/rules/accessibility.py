"""
Accessibility Rules.
"""
from typing import Any, Dict, List

from app.modules.scorer.services.base_rule import BaseRule
from app.modules.scorer.models.rule_result import RuleResult, Severity


class AltTextRule(BaseRule):
    """Check image alt text for accessibility."""
    rule_id = "a11y_001"
    name = "Image Alt Text"
    category = "accessibility"
    description = "Images must have alt text for screen readers"
    weight = 1.2
    tags = ["critical", "accessibility", "images"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        images = data.get("images", {})
        total_count = images.get("total_count", 0)
        without_alt = images.get("without_alt", 0)
        
        if total_count == 0:
            return [self._create_result(
                passed=True,
                message="No images to check",
                severity=Severity.INFO,
                score_impact=0,
            )]
        
        with_alt = total_count - without_alt
        coverage = (with_alt / total_count * 100) if total_count > 0 else 0
        
        if coverage >= 100:
            return [self._create_result(
                passed=True,
                message=f"All images have alt text ({total_count}/{total_count})",
                severity=Severity.PASSED,
                score_impact=1,
                data={"coverage": coverage},
            )]
        
        if coverage >= 80:
            return [self._create_result(
                passed=True,
                message=f"Good alt text coverage: {coverage:.1f}%",
                severity=Severity.PASSED,
                score_impact=0,
                data={"coverage": coverage, "missing": without_alt},
            )]
        
        impact = -min(without_alt * 2, 10)
        return [self._create_result(
            passed=False,
            message=f"{without_alt} images missing alt text ({coverage:.1f}% coverage)",
            severity=Severity.WARNING,
            score_impact=impact,
            recommendation="Add descriptive alt text to all images for accessibility",
            data={"coverage": coverage, "missing": without_alt},
        )]


class LanguageRule(BaseRule):
    """Check HTML lang attribute for accessibility."""
    rule_id = "a11y_002"
    name = "Page Language"
    category = "accessibility"
    description = "HTML must declare language for screen readers"
    weight = 1.0
    tags = ["critical", "accessibility", "language"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        basic = data.get("basic", {})
        language = basic.get("language", "")
        
        if not language:
            return [self._create_result(
                passed=False,
                message="HTML lang attribute not specified",
                severity=Severity.CRITICAL,
                score_impact=-8,
                recommendation="Add lang attribute to <html> tag (e.g., <html lang='en'>)",
            )]
        
        return [self._create_result(
            passed=True,
            message=f"Language declared: {language}",
            severity=Severity.PASSED,
            score_impact=0,
            data={"language": language},
        )]


class HeadingStructureRule(BaseRule):
    """Check heading structure for accessibility."""
    rule_id = "a11y_003"
    name = "Heading Structure"
    category = "accessibility"
    description = "Headings should be properly structured for screen readers"
    weight = 1.0
    tags = ["warning", "accessibility", "headings"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        headings = data.get("headings", {})
        heading_stats = headings.get("heading_stats", {})
        
        h1_count = len(headings.get("h1", []))
        h2_count = len(headings.get("h2", []))
        
        issues = []
        impact = 0
        
        if h1_count == 0:
            issues.append("Missing H1")
            impact -= 5
        
        if h1_count > 1:
            issues.append(f"Multiple H1 tags ({h1_count})")
            impact -= 3
        
        if not heading_stats.get("is_sequential", True):
            issues.append("Non-sequential heading levels")
            impact -= 3
        
        if not issues:
            return [self._create_result(
                passed=True,
                message="Heading structure is logical and accessible",
                severity=Severity.PASSED,
                score_impact=0,
            )]
        
        return [self._create_result(
            passed=False,
            message=f"Heading accessibility issues: {', '.join(issues)}",
            severity=Severity.WARNING,
            score_impact=impact,
            recommendation="Organize headings in logical hierarchy (H1 → H2 → H3) for screen readers",
        )]


class LinkTextRule(BaseRule):
    """Check link text for accessibility."""
    rule_id = "a11y_004"
    name = "Link Text"
    category = "accessibility"
    description = "Links should have descriptive text for screen readers"
    weight = 1.0
    tags = ["warning", "accessibility", "links"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        links = data.get("links", {})
        all_links = links.get("internal_links", []) + links.get("external_links", [])
        
        if not all_links:
            return [self._create_result(
                passed=True,
                message="No links to check",
                severity=Severity.INFO,
                score_impact=0,
            )]
        
        generic_anchors = ["click here", "read more", "here", "link", "more", "go"]
        problematic = []
        
        for link in all_links:
            anchor = link.get("anchor_text", "").lower().strip()
            if anchor in generic_anchors or len(anchor) < 3:
                problematic.append(anchor)
        
        if not problematic:
            return [self._create_result(
                passed=True,
                message="All links have descriptive text",
                severity=Severity.PASSED,
                score_impact=0,
            )]
        
        impact = -min(len(problematic) * 2, 8)
        return [self._create_result(
            passed=False,
            message=f"{len(problematic)} links have non-descriptive text",
            severity=Severity.WARNING,
            score_impact=impact,
            recommendation="Use descriptive link text for better accessibility and SEO",
            data={"problematic_count": len(problematic)},
        )]


class ColorContrastRule(BaseRule):
    """Check for color contrast (basic check)."""
    rule_id = "a11y_005"
    name = "Color Contrast"
    category = "accessibility"
    description = "Text should have sufficient color contrast"
    weight = 0.9
    tags = ["warning", "accessibility", "contrast"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        # This would require computed styles from the parser
        # For now, we return INFO as placeholder
        return [self._create_result(
            passed=True,
            message="Color contrast check (requires style analysis)",
            severity=Severity.INFO,
            score_impact=0,
            recommendation="Ensure text has WCAG AA compliant contrast ratio (4.5:1 minimum)",
        )]


class KeyboardNavigationRule(BaseRule):
    """Check for keyboard navigation support."""
    rule_id = "a11y_006"
    name = "Keyboard Navigation"
    category = "accessibility"
    description = "Page should support keyboard navigation"
    weight = 0.8
    tags = ["info", "accessibility", "keyboard"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        # This would require JavaScript execution to test
        return [self._create_result(
            passed=True,
            message="Keyboard navigation check (requires JavaScript execution)",
            severity=Severity.INFO,
            score_impact=0,
            recommendation="Ensure all interactive elements are keyboard accessible",
        )]


class ARIALabelsRule(BaseRule):
    """Check for ARIA labels."""
    rule_id = "a11y_007"
    name = "ARIA Labels"
    category = "accessibility"
    description = "Check for ARIA labels and roles"
    weight = 0.7
    tags = ["info", "accessibility", "aria"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        # This would require parsing ARIA attributes
        return [self._create_result(
            passed=True,
            message="ARIA labels check (requires attribute parsing)",
            severity=Severity.INFO,
            score_impact=0,
            recommendation="Add ARIA labels to improve screen reader experience",
        )]


class FormLabelsRule(BaseRule):
    """Check form labels for accessibility."""
    rule_id = "a11y_008"
    name = "Form Labels"
    category = "accessibility"
    description = "Form inputs should have associated labels"
    weight = 1.0
    tags = ["warning", "accessibility", "forms"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        # This would require form analysis from parser
        media = data.get("media", {})
        form_count = media.get("forms", 0)
        
        if form_count == 0:
            return [self._create_result(
                passed=True,
                message="No forms found",
                severity=Severity.INFO,
                score_impact=0,
            )]
        
        return [self._create_result(
            passed=False,
            message=f"{form_count} forms found - ensure all inputs have labels",
            severity=Severity.INFO,
            score_impact=-2,
            recommendation="Add <label> tags for all form inputs",
            data={"form_count": form_count},
        )]