"""
Links Analysis Rules.
"""
from typing import Any, Dict, List

from app.modules.scorer.services.base_rule import BaseRule
from app.modules.rule_engine.models.rule_result import RuleResult, Severity


class InternalLinksRule(BaseRule):
    """Check internal links count and quality."""
    rule_id = "links_001"
    name = "Internal Links"
    category = "links"
    description = "Page should have internal links for site structure"
    weight = 1.1
    tags = ["warning", "links", "navigation"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        links = data.get("links", {})
        internal_count = links.get("internal_count", 0)
        internal_links = links.get("internal_links", [])
        
        if internal_count == 0:
            return [self._create_result(
                passed=False,
                message="No internal links found",
                severity=Severity.WARNING,
                score_impact=-5,
                recommendation="Add internal links to other pages on your website",
            )]
        
        # Contextual link check
        contextual = sum(1 for link in internal_links 
                        if len(link.get("anchor_text", "")) > 10)
        contextual_ratio = contextual / internal_count if internal_count > 0 else 0
        
        details = {
            "internal_count": internal_count,
            "contextual_links": contextual,
            "contextual_ratio": round(contextual_ratio, 2),
        }
        
        if internal_count >= 10 and contextual_ratio >= 0.5:
            return [self._create_result(
                passed=True,
                message=f"Good internal linking ({internal_count} internal links, {contextual} contextual)",
                severity=Severity.PASSED,
                score_impact=1,
                data=details,
            )]
        
        if internal_count < 5:
            return [self._create_result(
                passed=False,
                message=f"Few internal links ({internal_count}, recommended: 10+)",
                severity=Severity.WARNING,
                score_impact=-3,
                recommendation="Add more internal links to improve site structure and user navigation",
                data=details,
            )]
        
        return [self._create_result(
            passed=True,
            message=f"Adequate internal linking ({internal_count} internal links)",
            severity=Severity.PASSED,
            score_impact=0,
            data=details,
        )]


class ExternalLinksRule(BaseRule):
    """Check external links."""
    rule_id = "links_002"
    name = "External Links"
    category = "links"
    description = "Check external linking behavior"
    weight = 0.8
    tags = ["info", "links", "outbound"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        links = data.get("links", {})
        external_count = links.get("external_count", 0)
        external_links = links.get("external_links", [])
        
        if external_count == 0:
            return [self._create_result(
                passed=False,
                message="No external links found",
                severity=Severity.INFO,
                score_impact=-1,
                recommendation="Consider linking to authoritative external sources",
            )]
        
        # Check if external links open in new tab
        external_new_tab = sum(1 for link in external_links if link.get("new_tab", False))
        external_same_tab = external_count - external_new_tab
        
        msg = f"Has {external_count} external links"
        if external_same_tab > 0 and external_new_tab > 0:
            msg += f" ({external_new_tab} open in new tab, {external_same_tab} in same tab)"
        
        return [self._create_result(
            passed=True,
            message=msg,
            severity=Severity.PASSED,
            score_impact=0,
            data={"external_count": external_count, "new_tab_count": external_new_tab},
        )]


class BrokenLinksRule(BaseRule):
    """Check for broken links."""
    rule_id = "links_003"
    name = "Broken Links"
    category = "links"
    description = "Check for broken internal and external links"
    weight = 1.3
    tags = ["critical", "links", "errors"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        links = data.get("links", {})
        broken_internal = links.get("broken_internal", [])
        broken_external = links.get("broken_external", [])
        
        if not broken_internal and not broken_external:
            return [self._create_result(
                passed=True,
                message="Live link check not enabled (broken link data unavailable)",
                severity=Severity.INFO,
                score_impact=0,
            )]
        
        total_broken = len(broken_internal) + len(broken_external)
        
        if total_broken == 0:
            return [self._create_result(
                passed=True,
                message="No broken links detected",
                severity=Severity.PASSED,
                score_impact=0,
            )]
        
        impact = -min(total_broken * 3, 15)
        broken_samples = broken_internal[:3] + broken_external[:2]
        
        return [self._create_result(
            passed=False,
            message=f"Found {total_broken} broken links ({len(broken_internal)} internal, {len(broken_external)} external)",
            severity=Severity.CRITICAL if total_broken > 5 else Severity.WARNING,
            score_impact=impact,
            recommendation=f"Fix {total_broken} broken links to improve user experience and SEO",
            data={"total_broken": total_broken, "samples": broken_samples},
        )]


class AnchorTextRule(BaseRule):
    """Check anchor text quality."""
    rule_id = "links_004"
    name = "Anchor Text"
    category = "links"
    description = "Links should have descriptive anchor text"
    weight = 1.0
    tags = ["warning", "links", "ux"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        links = data.get("links", {})
        all_links = links.get("internal_links", []) + links.get("external_links", [])
        
        if not all_links:
            return [self._create_result(
                passed=True,
                message="No links to analyze",
                severity=Severity.INFO,
                score_impact=0,
            )]
        
        # Check for generic anchor text
        generic_anchors = ["click here", "read more", "here", "link", "more"]
        generic_count = 0
        
        for link in all_links:
            anchor = link.get("anchor_text", "").lower().strip()
            if anchor in generic_anchors or len(anchor) < 3:
                generic_count += 1
        
        if generic_count == 0:
            return [self._create_result(
                passed=True,
                message="All links have descriptive anchor text",
                severity=Severity.PASSED,
                score_impact=0,
            )]
        
        impact = -min(generic_count * 2, 8)
        return [self._create_result(
            passed=False,
            message=f"{generic_count} links have generic/non-descriptive anchor text",
            severity=Severity.WARNING,
            score_impact=impact,
            recommendation="Use descriptive anchor text for better SEO and accessibility",
            data={"generic_count": generic_count, "total_links": len(all_links)},
        )]


class NofollowLinksRule(BaseRule):
    """Check nofollow usage."""
    rule_id = "links_005"
    name = "Nofollow Links"
    category = "links"
    description = "Check nofollow attribute usage"
    weight = 0.6
    tags = ["info", "links", "crawling"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        links = data.get("links", {})
        nofollow_count = links.get("nofollow_count", 0)
        total_count = links.get("internal_count", 0) + links.get("external_count", 0)
        
        if total_count == 0:
            return [self._create_result(
                passed=True,
                message="No links found",
                severity=Severity.INFO,
                score_impact=0,
            )]
        
        nofollow_ratio = nofollow_count / total_count if total_count > 0 else 0
        
        if nofollow_ratio > 0.5:
            return [self._create_result(
                passed=False,
                message=f"High nofollow ratio: {nofollow_ratio:.1%} of links are nofollow",
                severity=Severity.INFO,
                score_impact=-2,
                recommendation="Review nofollow usage - ensure important internal links are followed",
                data={"nofollow_count": nofollow_count, "total_count": total_count},
            )]
        
        return [self._create_result(
            passed=True,
            message=f"Nofollow links: {nofollow_count}/{total_count}",
            severity=Severity.INFO,
            score_impact=0,
            data={"nofollow_count": nofollow_count, "total_count": total_count},
        )]