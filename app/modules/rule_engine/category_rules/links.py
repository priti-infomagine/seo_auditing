"""
Links Analysis Rules.
"""
from typing import Any, Dict, List
import re
from urllib.parse import urlparse

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
        data_available = links.get("broken_link_data_available", False)
        
        if not data_available:
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
        generic_anchors = {
            "click here",
            "read more",
            "learn more",
            "here",
            "link",
            "more",
            "this",
            "this link",
            "website",
            "visit",
            "go",
            "details",
            "view more",
            "see more",
            "find out more",
        }

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



# ============================================================================
# NEW LINK RULES (6-15)
# ============================================================================

class DeadEndPagesRule(BaseRule):
    """Check for dead-end pages (pages with no outbound internal links)."""
    rule_id = "links_006"
    name = "Dead-End Pages"
    category = "links"
    description = "Pages should have at least one internal outbound link"
    weight = 1.2
    tags = ["warning", "links", "architecture"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        site_links = data.get("site_links", {})
        dead_end_pages = site_links.get("dead_end_pages", [])
        url = data.get("url", {}).get("normalized_url", "")
        
        if not dead_end_pages:
            return [self._create_result(
                passed=True,
                message="No dead-end pages detected in crawl",
                severity=Severity.PASSED,
                score_impact=0,
            )]
        
        # Check if current page is a dead end
        is_dead_end = url in dead_end_pages
        
        if is_dead_end:
            return [self._create_result(
                passed=False,
                message="Page is a dead end (no outbound internal links)",
                severity=Severity.WARNING,
                score_impact=-5,
                recommendation="Add internal links to other relevant pages on your site",
                data={"dead_end_pages_count": len(dead_end_pages)},
            )]
        
        return [self._create_result(
            passed=True,
            message="Page has outbound internal links",
            severity=Severity.PASSED,
            score_impact=0,
            data={"dead_end_pages_count": len(dead_end_pages)},
        )]


class FragmentLinkTargetsRule(BaseRule):
    """Check fragment link targets exist in rendered DOM."""
    rule_id = "links_007"
    name = "Fragment Link Targets"
    category = "links"
    description = "Fragment links (#id) should have matching DOM elements"
    weight = 0.9
    tags = ["warning", "links", "ux"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        links = data.get("links", {})
        all_links = links.get("internal_links", []) + links.get("external_links", [])
        
        # Use rendered links if available, fallback to static
        rendered_total = links.get("rendered_total_links", 0)
        fragment_count = links.get("fragment_link_count", 0)
        
        if fragment_count == 0:
            return [self._create_result(
                passed=True,
                message="No fragment links found",
                severity=Severity.INFO,
                score_impact=0,
            )]
        
        # Check fragment targets - in a real implementation, this would 
        # check if the ID exists in the rendered DOM
        # For now, we flag fragment links as a warning to review manually
        return [self._create_result(
            passed=False,
            message=f"Found {fragment_count} fragment link(s) - verify targets exist in rendered DOM",
            severity=Severity.WARNING,
            score_impact=-2,
            recommendation="Ensure fragment link targets (e.g., #section) have matching id attributes in the rendered HTML",
            data={"fragment_link_count": fragment_count, "rendered_links_available": rendered_total > 0},
        )]


class ExcessiveLinkCountRule(BaseRule):
    """Check for excessive link count on page."""
    rule_id = "links_008"
    name = "Excessive Link Count"
    category = "links"
    description = "Pages should not have excessive links (>100 recommended max)"
    weight = 0.8
    tags = ["warning", "links", "crawl_budget"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        from app.core.config import settings
        
        links = data.get("links", {})
        
        # Prefer rendered count if available
        total = links.get("rendered_total_links", 0) or links.get("total_links", 0)
        
        if total == 0:
            return [self._create_result(
                passed=True,
                message="No links found",
                severity=Severity.INFO,
                score_impact=0,
            )]
        
        critical_threshold = getattr(settings, "LINK_MAX_COUNT_CRITICAL_THRESHOLD", 200)
        warning_threshold = getattr(settings, "LINK_MAX_COUNT_THRESHOLD", 100)
        
        if total > critical_threshold:
            return [self._create_result(
                passed=False,
                message=f"Excessive link count: {total} links (recommended max: {warning_threshold})",
                severity=Severity.CRITICAL,
                score_impact=-10,
                recommendation="Reduce number of links to improve crawl budget and user experience",
                data={"total_links": total},
            )]
        
        if total > warning_threshold:
            return [self._create_result(
                passed=False,
                message=f"High link count: {total} links (recommended max: {warning_threshold})",
                severity=Severity.WARNING,
                score_impact=-5,
                recommendation="Consider reducing links to improve crawl efficiency",
                data={"total_links": total},
            )]
        
        return [self._create_result(
            passed=True,
            message=f"Link count within recommended limits: {total} links",
            severity=Severity.PASSED,
            score_impact=0,
            data={"total_links": total},
        )]


class NoLocalhostLinksRule(BaseRule):
    """Check for localhost/private IP links."""
    rule_id = "links_009"
    name = "No Localhost Links"
    category = "links"
    description = "Links should not point to localhost or private IPs"
    weight = 1.0
    tags = ["critical", "links", "security"]
    
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
        
        # Private IP ranges and localhost patterns
        localhost_patterns = [
            "localhost",
            "127.0.0.1",
            "::1",
            "0.0.0.0",
        ]
        
        private_ip_patterns = [
            r"^10\.\d+\.\d+\.\d+$",           # 10.0.0.0/8
            r"^172\.(1[6-9]|2[0-9]|3[0-1])\.\d+\.\d+$",  # 172.16.0.0/12
            r"^192\.168\.\d+\.\d+$",          # 192.168.0.0/16
            r"^169\.254\.\d+\.\d+$",          # Link-local
            r"^fe80::",                        # IPv6 link-local
        ]
        
        violations = []
        
        for link in all_links:
            # Use raw_href if available, fallback to absolute_url
            href = link.get("raw_href") or link.get("url") or link.get("absolute_url") or ""
            href_lower = href.lower()
            
            # Check localhost
            for pattern in localhost_patterns:
                if pattern in href_lower:
                    violations.append({"url": href, "reason": f"Contains localhost pattern: {pattern}"})
                    break
            
            # Check private IPs
            try:
                parsed = urlparse(href)
                hostname = parsed.hostname or ""
                for pattern in private_ip_patterns:
                    if re.match(pattern, hostname):
                        violations.append({"url": href, "reason": f"Private IP address: {hostname}"})
                        break
            except Exception:
                pass
        
        if not violations:
            return [self._create_result(
                passed=True,
                message="No localhost or private IP links found",
                severity=Severity.PASSED,
                score_impact=0,
            )]
        
        return [self._create_result(
            passed=False,
            message=f"Found {len(violations)} link(s) pointing to localhost or private IPs",
            severity=Severity.CRITICAL,
            score_impact=-10,
            recommendation="Remove or replace localhost/private IP links with production URLs",
            data={"violations": violations[:10]},  # Limit to first 10
        )]


class NoLocalFileLinksRule(BaseRule):
    """Check for file:// protocol links."""
    rule_id = "links_010"
    name = "No Local File Links"
    category = "links"
    description = "Links should not use file:// protocol"
    weight = 1.0
    tags = ["critical", "links", "security"]
    
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
        
        violations = []
        
        for link in all_links:
            href = link.get("raw_href") or link.get("url") or link.get("absolute_url") or ""
            if href.lower().startswith("file:"):
                violations.append({"url": href, "reason": "Uses file:// protocol"})
        
        if not violations:
            return [self._create_result(
                passed=True,
                message="No file:// protocol links found",
                severity=Severity.PASSED,
                score_impact=0,
            )]
        
        return [self._create_result(
            passed=False,
            message=f"Found {len(violations)} file:// protocol link(s)",
            severity=Severity.CRITICAL,
            score_impact=-10,
            recommendation="Replace file:// links with proper HTTP/HTTPS URLs",
            data={"violations": violations[:10]},
        )]


class NoOnclickNavigationRule(BaseRule):
    """Check for onclick navigation on links."""
    rule_id = "links_011"
    name = "No onclick Navigation"
    category = "links"
    description = "Links should not use onclick for navigation (use <a href>)"
    weight = 0.7
    tags = ["warning", "links", "accessibility"]
    
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
        
        violations = []
        
        for link in all_links:
            # Check raw_attributes for onclick
            raw_attrs = link.get("raw_attributes", {})
            onclick = raw_attrs.get("onclick", "") or raw_attrs.get("onClick", "")
            
            if onclick:
                # Check if it's a navigation pattern
                onclick_lower = onclick.lower()
                nav_patterns = [
                    "location.href",
                    "window.location",
                    "window.open",
                    "document.location",
                    "navigate",
                    "redirect",
                ]
                
                for pattern in nav_patterns:
                    if pattern in onclick_lower:
                        # Check if link has empty or placeholder href
                        href = link.get("raw_href") or link.get("href") or link.get("url") or ""
                        if not href or href.strip() in ("", "#", "javascript:void(0)", "javascript:;"):
                            violations.append({
                                "url": href,
                                "onclick": onclick[:200],
                                "reason": f"onclick navigation with empty href: {pattern}"
                            })
                            break
        
        if not violations:
            return [self._create_result(
                passed=True,
                message="No onclick navigation on empty-href links found",
                severity=Severity.PASSED,
                score_impact=0,
            )]
        
        return [self._create_result(
            passed=False,
            message=f"Found {len(violations)} link(s) using onclick for navigation with empty href",
            severity=Severity.WARNING,
            score_impact=-5,
            recommendation="Use proper <a href> for navigation; reserve onclick for JavaScript actions",
            data={"violations": violations[:10]},
        )]


class CleanLinkHrefsRule(BaseRule):
    """Check for clean HREF attributes."""
    rule_id = "links_012"
    name = "Clean Link HREFs"
    category = "links"
    description = "HREF attributes should not contain whitespace, control chars, or double encoding"
    weight = 0.6
    tags = ["info", "links", "quality"]
    
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
        
        violations = []
        
        for link in all_links:
            raw_href = link.get("raw_href", "")
            if not raw_href:
                continue
            
            issues = []
            
            # Leading/trailing whitespace
            if raw_href != raw_href.strip():
                issues.append("leading/trailing whitespace")
            
            # Control characters
            if any(ord(c) < 32 for c in raw_href):
                issues.append("control characters")
            
            # Double encoding (%25 = encoded %)
            if "%25" in raw_href:
                issues.append("double encoding (%25)")
            
            # Space not encoded
            if " " in raw_href:
                issues.append("unencoded spaces")
            
            # Newlines/tabs
            if "\n" in raw_href or "\r" in raw_href or "\t" in raw_href:
                issues.append("newlines/tabs")
            
            if issues:
                violations.append({
                    "url": raw_href,
                    "issues": issues
                })
        
        if not violations:
            return [self._create_result(
                passed=True,
                message="All HREF attributes are clean",
                severity=Severity.PASSED,
                score_impact=0,
            )]
        
        return [self._create_result(
            passed=False,
            message=f"Found {len(violations)} link(s) with dirty HREF attributes",
            severity=Severity.WARNING,
            score_impact=-3,
            recommendation="Clean HREF attributes: remove whitespace, encode spaces, fix double encoding",
            data={"violations": violations[:10]},
        )]


class NoHttpsDowngradeRule(BaseRule):
    """Check for HTTPS to HTTP downgrade on internal links."""
    rule_id = "links_013"
    name = "No HTTPS Downgrade"
    category = "links"
    description = "Internal links on HTTPS pages should not point to HTTP"
    weight = 1.1
    tags = ["warning", "links", "security"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        links = data.get("links", {})
        internal_links = links.get("internal_links", [])
        page_https = data.get("url", {}).get("https", False)
        
        if not page_https:
            return [self._create_result(
                passed=True,
                message="Page is not HTTPS, skipping HTTPS downgrade check",
                severity=Severity.INFO,
                score_impact=0,
            )]
        
        if not internal_links:
            return [self._create_result(
                passed=True,
                message="No internal links to check",
                severity=Severity.INFO,
                score_impact=0,
            )]
        
        violations = []
        
        for link in internal_links:
            href = link.get("url") or link.get("absolute_url") or link.get("raw_href") or ""
            if href.lower().startswith("http://"):
                violations.append({
                    "url": href,
                    "reason": "Internal link uses HTTP on HTTPS page"
                })
        
        if not violations:
            return [self._create_result(
                passed=True,
                message="No HTTPS downgrade links found",
                severity=Severity.PASSED,
                score_impact=0,
            )]
        
        return [self._create_result(
            passed=False,
            message=f"Found {len(violations)} internal link(s) using HTTP on HTTPS page",
            severity=Severity.WARNING,
            score_impact=-5,
            recommendation="Update internal links to use HTTPS to avoid mixed content warnings",
            data={"violations": violations[:10]},
        )]


class ValidPhoneEmailLinksRule(BaseRule):
    """Check tel: and mailto: links for valid formats."""
    rule_id = "links_014"
    name = "Valid Phone & Email Links"
    category = "links"
    description = "tel: and mailto: links should have valid formats"
    weight = 0.8
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
        
        tel_pattern = re.compile(r"^tel:\+?[1-9]\d{1,14}$")
        mailto_pattern = re.compile(r"^mailto:[^@\s]+@[^@\s]+\.[^@\s]+$")
        
        tel_violations = []
        mailto_violations = []
        
        for link in all_links:
            href = link.get("raw_href") or link.get("url") or link.get("absolute_url") or ""
            href_lower = href.lower()
            
            if href_lower.startswith("tel:"):
                if not tel_pattern.match(href_lower):
                    tel_violations.append({"url": href, "reason": "Invalid tel: format (should be E.164: tel:+1234567890)"})
            
            elif href_lower.startswith("mailto:"):
                if not mailto_pattern.match(href_lower):
                    mailto_violations.append({"url": href, "reason": "Invalid mailto: format"})
        
        total_violations = len(tel_violations) + len(mailto_violations)
        
        if total_violations == 0:
            return [self._create_result(
                passed=True,
                message="All tel: and mailto: links have valid formats",
                severity=Severity.PASSED,
                score_impact=0,
            )]
        
        return [self._create_result(
            passed=False,
            message=f"Found {len(tel_violations)} invalid tel: and {len(mailto_violations)} invalid mailto: link(s)",
            severity=Severity.WARNING,
            score_impact=-3,
            recommendation="Fix tel: links to use E.164 format (+country code), fix mailto: to valid email format",
            data={"tel_violations": tel_violations[:5], "mailto_violations": mailto_violations[:5]},
        )]


class UrlDepthRule(BaseRule):
    """Check URL path depth."""
    rule_id = "links_015"
    name = "URL Depth"
    category = "links"
    description = "URL path depth should not exceed 4 levels for optimal crawlability"
    weight = 0.7
    tags = ["info", "links", "architecture"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        from app.core.config import settings
        
        url = data.get("url", {}).get("normalized_url", "") or data.get("url", {}).get("url", "")
        
        if not url:
            return [self._create_result(
                passed=True,
                message="No URL to analyze",
                severity=Severity.INFO,
                score_impact=0,
            )]
        
        try:
            parsed = urlparse(url)
            path = parsed.path or ""
            
            # Count path segments (ignore empty from leading/trailing slashes)
            segments = [s for s in path.split("/") if s]
            depth = len(segments)
            
            warning_threshold = getattr(settings, "URL_MAX_DEPTH_WARNING_THRESHOLD", 6)
            recommended_threshold = getattr(settings, "URL_MAX_DEPTH_THRESHOLD", 4)
            
            if depth > warning_threshold:
                return [self._create_result(
                    passed=False,
                    message=f"URL depth too deep: {depth} levels (path: {path})",
                    severity=Severity.WARNING,
                    score_impact=-5,
                    recommendation=f"Flatten URL structure - keep depth ≤ {recommended_threshold} for better crawlability",
                    data={"depth": depth, "path": path, "segments": segments},
                )]
            
            if depth > recommended_threshold:
                return [self._create_result(
                    passed=False,
                    message=f"URL depth exceeds recommended: {depth} levels (path: {path})",
                    severity=Severity.INFO,
                    score_impact=-2,
                    recommendation=f"Consider flattening URL structure to ≤ {recommended_threshold} levels",
                    data={"depth": depth, "path": path, "segments": segments},
                )]
            
            return [self._create_result(
                passed=True,
                message=f"URL depth optimal: {depth} levels",
                severity=Severity.PASSED,
                score_impact=0,
                data={"depth": depth, "path": path},
            )]
        
        except Exception as exc:
            return [self._create_result(
                passed=True,
                message=f"Could not analyze URL depth: {exc}",
                severity=Severity.INFO,
                score_impact=0,
            )]