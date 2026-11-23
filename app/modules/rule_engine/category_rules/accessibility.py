"""
Accessibility Rules - 12 rules for WCAG 2.1 compliance.
"""
from typing import Any, Dict, List

from app.modules.scorer.services.base_rule import BaseRule
from app.modules.rule_engine.models.rule_result import RuleResult, Severity
import re

class FormLabelsRule(BaseRule):
    """a11y_001 - Form inputs have associated accessible labels."""
    rule_id = "a11y_001"
    name = "Form Labels"
    category = "accessibility"
    description = "Form inputs must have associated accessible labels (label[for], wrapping label, aria-label, aria-labelledby, title)"
    weight = 1.5
    tags = ["critical", "accessibility", "forms", "wcag_3_3_2"]

    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        forms = data.get("forms", [])
        if not forms:
            return [self._create_result(
                passed=True,
                message="No forms found",
                severity=Severity.INFO,
                score_impact=0,
            )]

        total_fields = 0
        fields_with_accessible_name = 0
        fields_missing_name = []

        for form in forms:
            for field in form.get("fields", []):
                total_fields += 1
                if field.get("accessible_name"):
                    fields_with_accessible_name += 1
                else:
                    fields_missing_name.append({
                        "tag": field.get("tag"),
                        "type": field.get("type"),
                        "id": field.get("id"),
                        "name": field.get("name"),
                    })

        if total_fields == 0:
            return [self._create_result(
                passed=True,
                message="No form fields to check",
                severity=Severity.INFO,
                score_impact=0,
            )]

        coverage = (fields_with_accessible_name / total_fields * 100) if total_fields > 0 else 0

        if coverage >= 100:
            return [self._create_result(
                passed=True,
                message=f"All {total_fields} form fields have accessible names",
                severity=Severity.PASSED,
                score_impact=2,
                data={"coverage": coverage, "total_fields": total_fields},
            )]

        if coverage >= 80:
            return [self._create_result(
                passed=True,
                message=f"Good form label coverage: {coverage:.1f}% ({fields_with_accessible_name}/{total_fields})",
                severity=Severity.PASSED,
                score_impact=1,
                data={"coverage": coverage, "missing": total_fields - fields_with_accessible_name},
            )]

        impact = -min((total_fields - fields_with_accessible_name) * 2, 15)
        return [self._create_result(
            passed=False,
            message=f"{total_fields - fields_with_accessible_name} of {total_fields} form fields missing accessible names ({coverage:.1f}% coverage)",
            severity=Severity.WARNING,
            score_impact=impact,
            recommendation="Ensure all form inputs have associated labels via label[for], wrapping <label>, aria-label, aria-labelledby, or title attribute",
            data={"coverage": coverage, "missing": total_fields - fields_with_accessible_name, "missing_fields": fields_missing_name[:10]},
        )]


class ARIALabelsRule(BaseRule):
    """a11y_002 - Interactive elements have accessible names."""
    rule_id = "a11y_002"
    name = "ARIA Labels"
    category = "accessibility"
    description = "Interactive elements (links, buttons, custom widgets) must have accessible names via aria-label, aria-labelledby, or text content"
    weight = 1.3
    tags = ["critical", "accessibility", "aria", "wcag_4_1_2"]

    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        aria_attrs = data.get("aria_attributes", {})
        labels = aria_attrs.get("labels", [])
        links = data.get("links", {})
        buttons = data.get("buttons", [])

        # Check links for accessible names
        all_links = links.get("internal_links", []) + links.get("external_links", [])
        links_without_name = 0
        for link in all_links:
            anchor = link.get("anchor_text", "").strip()
            aria_label = link.get("aria_label", "").strip()
            aria_labelledby = link.get("aria_labelledby", "").strip()
            title = link.get("title", "").strip()
            if not (anchor or aria_label or aria_labelledby or title):
                links_without_name += 1

        # Check buttons for accessible names
        buttons_without_name = 0
        for btn in buttons:
            if not btn.get("has_accessible_name", False):
                buttons_without_name += 1

        total_interactive = len(all_links) + len(buttons)
        total_missing = links_without_name + buttons_without_name

        if total_interactive == 0:
            return [self._create_result(
                passed=True,
                message="No interactive elements to check",
                severity=Severity.INFO,
                score_impact=0,
            )]

        if total_missing == 0:
            return [self._create_result(
                passed=True,
                message=f"All {total_interactive} interactive elements have accessible names",
                severity=Severity.PASSED,
                score_impact=2,
                data={"links_checked": len(all_links), "buttons_checked": len(buttons)},
            )]

        impact = -min(total_missing * 2, 12)
        return [self._create_result(
            passed=False,
            message=f"{total_missing} of {total_interactive} interactive elements missing accessible names",
            severity=Severity.WARNING,
            score_impact=impact,
            recommendation="Ensure all links have descriptive text or aria-label/aria-labelledby, and all buttons have accessible names",
            data={"links_missing": links_without_name, "buttons_missing": buttons_without_name},
        )]


class ColorContrastRule(BaseRule):
    """a11y_003 - Text and background have sufficient contrast."""
    rule_id = "a11y_003"
    name = "Color Contrast"
    category = "accessibility"
    description = "Text must have sufficient color contrast ratio (WCAG AA: 4.5:1 normal, 3:1 large). Static analysis only - requires browser tools for full validation."
    weight = 1.0
    tags = ["warning", "accessibility", "contrast", "wcag_1_4_3"]

    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        # Static analysis cannot compute actual contrast ratios
        # This rule serves as a reminder to test with automated tools
        return [self._create_result(
            passed=True,
            message="Color contrast requires computed styles analysis (use axe, Lighthouse, or browser devtools for full validation)",
            severity=Severity.INFO,
            score_impact=0,
            recommendation="Test color contrast with automated tools: axe-core, Lighthouse, or browser DevTools. Ensure 4.5:1 ratio for normal text, 3:1 for large text (18pt+ or 14pt+ bold).",
            data={"note": "Static analysis limitation - cannot compute actual contrast ratios from HTML/CSS alone"},
        )]


class KeyboardNavigationRule(BaseRule):
    """a11y_004 - Interactive elements can be accessed using a keyboard."""
    rule_id = "a11y_004"
    name = "Keyboard Navigation"
    category = "accessibility"
    description = "All interactive elements must be reachable and operable via keyboard. Static checks for tabindex, aria-hidden, and focusable elements."
    weight = 1.2
    tags = ["critical", "accessibility", "keyboard", "wcag_2_1_1"]

    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        html = data.get("html", "")
        issues = []

        # Check for tabindex="-1" on interactive elements (removes from tab order)
        import re
        tabindex_negative = re.findall(r'tabindex\s*=\s*["\']?-1["\']?', html, re.IGNORECASE)
        if tabindex_negative:
            issues.append(f"Found {len(tabindex_negative)} elements with tabindex='-1' (removed from keyboard navigation)")

        # Check for aria-hidden="true" on interactive elements
        aria_hidden = re.findall(r'aria-hidden\s*=\s*["\']?true["\']?', html, re.IGNORECASE)
        if aria_hidden:
            issues.append(f"Found {len(aria_hidden)} elements with aria-hidden='true' (hidden from screen readers)")

        # Check for outline: none or outline: 0 in inline styles (removes focus indicator)
        outline_none = re.findall(r'outline\s*:\s*(0|none)', html, re.IGNORECASE)
        if outline_none:
            issues.append(f"Found {len(outline_none)} instances of outline: none/0 (may remove focus visibility)")

        if not issues:
            return [self._create_result(
                passed=True,
                message="No obvious keyboard navigation blockers found in static analysis",
                severity=Severity.PASSED,
                score_impact=1,
                recommendation="Verify keyboard navigation manually: tab through page, ensure all interactive elements are reachable and operable",
            )]

        impact = -min(len(issues) * 3, 10)
        return [self._create_result(
            passed=False,
            message=f"Potential keyboard navigation issues: {'; '.join(issues)}",
            severity=Severity.WARNING,
            score_impact=impact,
            recommendation="Ensure all interactive elements are keyboard accessible: no tabindex='-1' on interactive elements, no aria-hidden='true' on focusable elements, preserve focus outlines",
            data={"issues": issues},
        )]


class FocusVisibilityRule(BaseRule):
    """a11y_005 - Keyboard focus indicators are visible."""
    rule_id = "a11y_005"
    name = "Focus Visibility"
    category = "accessibility"
    description = "Focus indicators must be visible for keyboard users. Checks for CSS that removes outlines."
    weight = 1.0
    tags = ["warning", "accessibility", "focus", "wcag_2_4_7"]

    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        html = data.get("html", "")
        inline_css = data.get("inline_css", [])
        inline_css_rendered = data.get("inline_css_rendered", [])

        issues = []

        # Check inline CSS for outline removal
        all_css = inline_css + inline_css_rendered
        for css_block in all_css:
            css_text = css_block.get("content", "") if isinstance(css_block, dict) else str(css_block)
            if re.search(r'outline\s*:\s*(0|none)\b', css_text, re.IGNORECASE):
                issues.append("Found 'outline: none' or 'outline: 0' in inline CSS")
                break

        # Check for :focus styles that might remove visibility
        for css_block in all_css:
            css_text = css_block.get("content", "") if isinstance(css_block, dict) else str(css_block)
            if re.search(r':focus\s*\{[^}]*outline\s*:\s*(0|none)', css_text, re.IGNORECASE):
                issues.append("Found :focus rule removing outline")
                break

        if not issues:
            return [self._create_result(
                passed=True,
                message="No obvious focus visibility removal found in inline CSS",
                severity=Severity.PASSED,
                score_impact=1,
                recommendation="Verify focus indicators are visible in browser: tab through page and check focus rings",
            )]

        impact = -min(len(issues) * 2, 8)
        return [self._create_result(
            passed=False,
            message=f"Focus visibility concerns: {'; '.join(issues)}",
            severity=Severity.WARNING,
            score_impact=impact,
            recommendation="Ensure focus indicators are visible: don't remove outlines without providing alternative focus styles (box-shadow, border, background change)",
            data={"issues": issues},
        )]


class HeadingAccessibilityRule(BaseRule):
    """a11y_006 - Headings are meaningful and follow a logical hierarchy."""
    rule_id = "a11y_006"
    name = "Heading Accessibility"
    category = "accessibility"
    description = "Headings must be properly structured (H1→H2→H3) and have meaningful text for screen reader navigation"
    weight = 1.2
    tags = ["critical", "accessibility", "headings", "wcag_1_3_1"]

    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        headings = data.get("headings", {})
        heading_stats = headings.get("heading_stats", {})

        h1_count = len(headings.get("h1", []))
        h1_texts = headings.get("h1", [])
        h2_count = len(headings.get("h2", []))
        h3_count = len(headings.get("h3", []))

        issues = []
        impact = 0

        if h1_count == 0:
            issues.append("Missing H1 heading")
            impact -= 5
        elif h1_count > 1:
            issues.append(f"Multiple H1 headings ({h1_count})")
            impact -= 3

        # Check for empty heading text
        empty_headings = 0
        for level in range(1, 7):
            for h_text in headings.get(f"h{level}", []):
                if not h_text or not h_text.strip():
                    empty_headings += 1
        if empty_headings > 0:
            issues.append(f"{empty_headings} heading(s) have empty text")
            impact -= empty_headings * 2

        # Check heading hierarchy
        if not heading_stats.get("is_sequential", True):
            issues.append("Non-sequential heading levels (skipping levels)")
            impact -= 3

        if not issues:
            return [self._create_result(
                passed=True,
                message=f"Heading structure is logical: H1({h1_count}) H2({h2_count}) H3({h3_count})",
                severity=Severity.PASSED,
                score_impact=1,
                data={"h1_count": h1_count, "h2_count": h2_count, "h3_count": h3_count},
            )]

        impact = max(impact, -12)
        return [self._create_result(
            passed=False,
            message=f"Heading accessibility issues: {', '.join(issues)}",
            severity=Severity.WARNING,
            score_impact=impact,
            recommendation="Use logical heading hierarchy: one H1, then H2, H3 sequentially. Ensure all headings have meaningful text",
            data={"h1_count": h1_count, "h2_count": h2_count, "h3_count": h3_count, "empty_headings": empty_headings},
        )]


class LandmarkRegionsRule(BaseRule):
    """a11y_007 - Page uses appropriate landmarks such as main, nav, and footer."""
    rule_id = "a11y_007"
    name = "Landmark Regions"
    category = "accessibility"
    description = "Page should use landmark regions (main, nav, header, footer, aside, section, form, search) for screen reader navigation"
    weight = 1.1
    tags = ["warning", "accessibility", "landmarks", "wcag_1_3_1"]

    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        landmarks = data.get("landmarks", [])
        content = data.get("content", {})

        # Expected landmarks
        expected_landmarks = {"main", "navigation", "banner", "contentinfo"}
        found_types = set()
        landmarks_with_names = 0

        for lm in landmarks:
            lm_type = lm.get("type", "").lower()
            if lm_type:
                found_types.add(lm_type)
            if lm.get("has_accessible_name", False):
                landmarks_with_names += 1

        issues = []
        impact = 0

        # Check for main landmark
        if "main" not in found_types and not content.get("has_main", False):
            issues.append("Missing main landmark (use <main> or role='main')")
            impact -= 4

        # Check for navigation
        if "navigation" not in found_types and not content.get("has_nav", False):
            issues.append("Missing navigation landmark (use <nav> or role='navigation')")
            impact -= 3

        # Check for header/banner
        if "banner" not in found_types and not content.get("has_header", False):
            issues.append("Missing header/banner landmark (use <header> or role='banner')")
            impact -= 2

        # Check for footer/contentinfo
        if "contentinfo" not in found_types and not content.get("has_footer", False):
            issues.append("Missing footer/contentinfo landmark (use <footer> or role='contentinfo')")
            impact -= 2

        if not issues:
            return [self._create_result(
                passed=True,
                message=f"All expected landmarks present: {', '.join(sorted(found_types))}",
                severity=Severity.PASSED,
                score_impact=1,
                data={"landmarks_found": list(found_types), "landmarks_with_names": landmarks_with_names},
            )]

        impact = max(impact, -10)
        return [self._create_result(
            passed=False,
            message=f"Missing landmark regions: {'; '.join(issues)}",
            severity=Severity.WARNING,
            score_impact=impact,
            recommendation="Add landmark regions: <main> for primary content, <nav> for navigation, <header> for header, <footer> for footer. Use ARIA roles as fallback",
            data={"landmarks_found": list(found_types), "missing": list(expected_landmarks - found_types)},
        )]


class LinkTextAccessibilityRule(BaseRule):
    """a11y_008 - Links have meaningful text instead of vague labels."""
    rule_id = "a11y_008"
    name = "Link Text Accessibility"
    category = "accessibility"
    description = "Link text must be descriptive and meaningful out of context (avoid 'click here', 'read more', etc.)"
    weight = 1.0
    tags = ["warning", "accessibility", "links", "wcag_2_4_4"]

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

        generic_anchors = {"click here", "read more", "here", "link", "more", "go", "click", "view", "see more", "learn more", "details", "info"}
        problematic = []

        for link in all_links:
            anchor = link.get("anchor_text", "").lower().strip()
            aria_label = link.get("aria_label", "").lower().strip()
            aria_labelledby = link.get("aria_labelledby", "").strip()
            title = link.get("title", "").lower().strip()

            # Use accessible name if available
            accessible_name = aria_label or title or anchor

            if accessible_name in generic_anchors or len(accessible_name) < 3:
                problematic.append({
                    "url": link.get("absolute_url", link.get("href", "")),
                    "anchor": anchor[:50],
                    "accessible_name": accessible_name[:50],
                })

        if not problematic:
            return [self._create_result(
                passed=True,
                message=f"All {len(all_links)} links have descriptive text",
                severity=Severity.PASSED,
                score_impact=1,
            )]

        impact = -min(len(problematic) * 2, 10)
        return [self._create_result(
            passed=False,
            message=f"{len(problematic)} of {len(all_links)} links have non-descriptive text",
            severity=Severity.WARNING,
            score_impact=impact,
            recommendation="Use descriptive link text that makes sense out of context. Avoid 'click here', 'read more', 'here'. Use aria-label if visual design requires brief text",
            data={"problematic_count": len(problematic), "examples": problematic[:5]},
        )]


class SkipNavigationLinkRule(BaseRule):
    """a11y_009 - A skip-to-content link is available for keyboard users."""
    rule_id = "a11y_009"
    name = "Skip Navigation Link"
    category = "accessibility"
    description = "Page must have a skip-to-content link as the first focusable element for keyboard users to bypass navigation"
    weight = 1.0
    tags = ["critical", "accessibility", "skip_link", "wcag_2_4_1"]

    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        skip_links = data.get("skip_links", [])

        if not skip_links:
            return [self._create_result(
                passed=False,
                message="No skip navigation link found",
                severity=Severity.WARNING,
                score_impact=-8,
                recommendation="Add a skip-to-content link as the first focusable element: <a href='#main' class='skip-link'>Skip to main content</a>",
                data={"has_skip_link": False},
            )]

        # Check if first focusable
        first_focusable = any(sl.get("is_first_focusable", False) for sl in skip_links)

        if first_focusable:
            return [self._create_result(
                passed=True,
                message="Skip navigation link present and appears to be first focusable element",
                severity=Severity.PASSED,
                score_impact=1,
                data={"has_skip_link": True, "first_focusable": True, "count": len(skip_links)},
            )]

        return [self._create_result(
            passed=True,
            message=f"Skip navigation link found ({len(skip_links)}) but may not be first focusable element",
            severity=Severity.WARNING,
            score_impact=0,
            recommendation="Ensure skip link is the first focusable element on the page (place at top of body, before navigation)",
            data={"has_skip_link": True, "first_focusable": False, "count": len(skip_links)},
        )]


class ButtonAccessibilityRule(BaseRule):
    """a11y_010 - Buttons have accessible names."""
    rule_id = "a11y_010"
    name = "Button Accessibility"
    category = "accessibility"
    description = "All buttons must have accessible names (text content, aria-label, aria-labelledby, title, or value for input buttons)"
    weight = 1.3
    tags = ["critical", "accessibility", "buttons", "wcag_4_1_2"]

    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        buttons = data.get("buttons", [])

        if not buttons:
            return [self._create_result(
                passed=True,
                message="No buttons found",
                severity=Severity.INFO,
                score_impact=0,
            )]

        buttons_without_name = []
        for btn in buttons:
            if not btn.get("has_accessible_name", False):
                buttons_without_name.append({
                    "tag": btn.get("tag"),
                    "type": btn.get("type"),
                    "id": btn.get("id"),
                })

        if not buttons_without_name:
            return [self._create_result(
                passed=True,
                message=f"All {len(buttons)} buttons have accessible names",
                severity=Severity.PASSED,
                score_impact=2,
                data={"total_buttons": len(buttons)},
            )]

        impact = -min(len(buttons_without_name) * 3, 12)
        return [self._create_result(
            passed=False,
            message=f"{len(buttons_without_name)} of {len(buttons)} buttons missing accessible names",
            severity=Severity.WARNING,
            score_impact=impact,
            recommendation="Ensure all buttons have accessible names: use text content for <button>, value for <input type=button>, aria-label, aria-labelledby, or title attribute",
            data={"total_buttons": len(buttons), "missing": len(buttons_without_name), "examples": buttons_without_name[:5]},
        )]


class IframeAccessibilityRule(BaseRule):
    """a11y_011 - Iframes have descriptive title attributes."""
    rule_id = "a11y_011"
    name = "Iframe Accessibility"
    category = "accessibility"
    description = "All iframes must have a descriptive title attribute for screen reader users to understand the embedded content"
    weight = 1.0
    tags = ["warning", "accessibility", "iframe", "wcag_4_1_2"]

    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        iframes = data.get("iframes", [])

        if not iframes:
            return [self._create_result(
                passed=True,
                message="No iframes found",
                severity=Severity.INFO,
                score_impact=0,
            )]

        iframes_without_title = [iframe for iframe in iframes if not iframe.get("has_title", False)]

        if not iframes_without_title:
            return [self._create_result(
                passed=True,
                message=f"All {len(iframes)} iframes have descriptive titles",
                severity=Severity.PASSED,
                score_impact=1,
                data={"total_iframes": len(iframes)},
            )]

        impact = -min(len(iframes_without_title) * 3, 10)
        return [self._create_result(
            passed=False,
            message=f"{len(iframes_without_title)} of {len(iframes)} iframes missing title attribute",
            severity=Severity.WARNING,
            score_impact=impact,
            recommendation="Add descriptive title attribute to all iframes: <iframe title='Description of embedded content' src='...'></iframe>",
            data={"total_iframes": len(iframes), "missing_title": len(iframes_without_title)},
        )]


class ViewportZoomAccessibilityRule(BaseRule):
    """a11y_012 - The page does not prevent users from zooming."""
    rule_id = "a11y_012"
    name = "Viewport Zoom Accessibility"
    category = "accessibility"
    description = "Viewport meta tag must not disable zoom (user-scalable=no, maximum-scale=1, minimum-scale=1) to support low-vision users"
    weight = 1.2
    tags = ["critical", "accessibility", "viewport", "wcag_1_4_4"]

    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        viewport_zoom_allows = data.get("viewport_zoom_allows", True)
        viewport = data.get("basic", {}).get("viewport", "")

        if viewport_zoom_allows:
            return [self._create_result(
                passed=True,
                message="Viewport allows zoom (no user-scalable=no or restrictive scales)",
                severity=Severity.PASSED,
                score_impact=1,
                data={"viewport": viewport},
            )]

        return [self._create_result(
            passed=False,
            message="Viewport meta tag prevents zooming (user-scalable=no or maximum-scale<=1)",
            severity=Severity.WARNING,
            score_impact=-8,
            recommendation="Remove user-scalable=no and maximum-scale restrictions from viewport meta tag. Allow users to zoom for accessibility",
            data={"viewport": viewport, "allows_zoom": False},
        )]