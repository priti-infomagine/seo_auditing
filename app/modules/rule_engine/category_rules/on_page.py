"""
On-Page SEO Rules.
"""
from typing import Any, Dict, List

from app.modules.scorer.services.base_rule import BaseRule
from app.modules.rule_engine.models.rule_result import RuleResult, Severity


class TitleTagRule(BaseRule):
    """Check title tag presence, length, pixel width, and quality."""
    rule_id = "on_page_001"
    name = "Title Tag"
    category = "on_page"
    description = "Page must have a descriptive title tag with optimal length and pixel width"
    weight = 1.5
    tags = ["critical", "on_page", "title"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        basic = data.get("basic", {})
        title = basic.get("title", "")
        title_length = basic.get("title_length", len(title) if title else 0)
        content = data.get("content", {})
        content_text = content.get("text", "") or content.get("normalized_text", "")
        
        if not title or not title.strip():
            return [self._create_result(
                passed=False,
                message="Missing page title tag",
                severity=Severity.CRITICAL,
                score_impact=-15,
                recommendation="Add a descriptive <title> tag (50-60 characters, include primary keyword)",
            )]
        
        pixel_width = self._estimate_pixel_width(title)
        issues = []
        impacts = 0
        details = {
            "title": title,
            "character_count": title_length,
            "pixel_width_estimate": pixel_width,
        }
        
        # Length checks
        if title_length < 30:
            issues.append("too short")
            impacts -= 3
        elif title_length <= 49:
            issues.append("acceptable length")
        elif title_length <= 60:
            issues.append("ideal length")
            details["length_status"] = "ideal"
        elif title_length <= 70:
            issues.append("slightly long")
            impacts -= 3
        else:
            issues.append("too long")
            impacts -= 5
        
        # Pixel width check (takes precedence for truncation risk)
        if pixel_width > 600:
            issues.append("likely truncated in SERP")
            impacts -= 3
            details["truncation_risk"] = True
        
        # Generic title check
        generic_titles = ["welcome", "home", "untitled", "page", "index", "new page", "default"]
        if title.lower().strip() in generic_titles:
            issues.append("generic title")
            impacts -= 3
            details["generic"] = True
        
        # Keyword/topic presence (if keyword data available)
        target_keyword = data.get("target_keyword") or data.get("keyword")
        if target_keyword:
            keyword_present = target_keyword.lower() in title.lower()
            details["keyword_present"] = keyword_present
            if not keyword_present:
                issues.append("missing target keyword")
                impacts -= 2
        
        # Title/content consistency
        if content_text and len(content_text) > 50:
            title_words = title.lower().split()[:5]
            content_lower = content_text.lower()
            consistency_hits = sum(1 for w in title_words if w in content_lower)
            details["content_consistency_score"] = consistency_hits / len(title_words) if title_words else 0
            if consistency_hits == 0:
                issues.append("title may not describe content")
                impacts -= 2
        
        if not issues or (len(issues) == 1 and "acceptable length" in issues):
            msg = f"Title length is optimal ({title_length} characters, ~{pixel_width}px)"
            return [self._create_result(
                passed=True,
                message=msg,
                severity=Severity.PASSED,
                score_impact=0,
                data=details,
            )]
        
        severity = Severity.WARNING if impacts > -8 else Severity.CRITICAL
        msg = f"Title issues: {', '.join(i for i in issues if i not in ('acceptable length',))}"
        if title_length >= 50 and title_length <= 60:
            msg = f"Title length is optimal ({title_length} characters), but: {', '.join(i for i in issues if i not in ('acceptable length', 'ideal length'))}"
        
        return [self._create_result(
            passed=False,
            message=msg,
            severity=severity,
            score_impact=impacts,
            recommendation="Adjust title: 50-60 characters, include primary keyword, avoid truncation",
            data=details,
        )]
    
    @staticmethod
    def _estimate_pixel_width(text: str) -> int:
        """Estimate pixel width of title for SERP display.
        
        Uses proportional font heuristic (~6.5px average per character).
        Google desktop SERP typically allows ~580-600px for titles.
        """
        if not text:
            return 0
        return int(len(text) * 6.5)


class MetaDescriptionRule(BaseRule):
    """Check meta description presence, length, pixel width, and quality."""
    rule_id = "on_page_002"
    name = "Meta Description"
    category = "on_page"
    description = "Page must have meta description with optimal length (140-160 chars)"
    weight = 1.2
    tags = ["critical", "on_page", "meta"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        basic = data.get("basic", {})
        meta_desc = basic.get("meta_description", "")
        meta_desc_length = basic.get("meta_description_length", len(meta_desc) if meta_desc else 0)
        
        if not meta_desc or not meta_desc.strip():
            return [self._create_result(
                passed=False,
                message="Missing meta description",
                severity=Severity.CRITICAL,
                score_impact=-12,
                recommendation="Add a compelling meta description (140-160 characters)",
            )]
        
        pixel_width = self._estimate_pixel_width(meta_desc)
        impacts = 0
        details = {
            "meta_description": meta_desc,
            "character_count": meta_desc_length,
            "pixel_width_estimate": pixel_width,
        }
        
        if meta_desc_length < 70:
            impacts -= 3
            details["length_status"] = "too_short"
        elif meta_desc_length <= 139:
            impacts -= 1
            details["length_status"] = "acceptable"
        elif meta_desc_length <= 160:
            impacts += 0
            details["length_status"] = "preferred"
        elif meta_desc_length <= 180:
            impacts -= 2
            details["length_status"] = "slightly_long"
        else:
            impacts -= 4
            details["length_status"] = "too_long"
        
        if pixel_width > 920:
            impacts -= 2
            details["truncation_risk"] = True
        
        target_keyword = data.get("target_keyword") or data.get("keyword")
        if target_keyword:
            keyword_present = target_keyword.lower() in meta_desc.lower()
            details["keyword_present"] = keyword_present
            if not keyword_present:
                impacts -= 1
        
        if impacts == 0 and meta_desc_length >= 140 and meta_desc_length <= 160:
            return [self._create_result(
                passed=True,
                message=f"Meta description length is optimal ({meta_desc_length} characters, ~{pixel_width}px)",
                severity=Severity.PASSED,
                score_impact=0,
                data=details,
            )]
        
        severity = Severity.WARNING if impacts > -6 else Severity.CRITICAL
        return [self._create_result(
            passed=False,
            message=f"Meta description length is {meta_desc_length} characters (recommended: 140-160)",
            severity=severity,
            score_impact=impacts,
            recommendation="Adjust meta description to 140-160 characters for optimal SERP display",
            data=details,
        )]
    
    @staticmethod
    def _estimate_pixel_width(text: str) -> int:
        if not text:
            return 0
        return int(len(text) * 6.5)


class H1TagRule(BaseRule):
    """Check H1 tag presence, count, length, and quality."""
    rule_id = "on_page_003"
    name = "H1 Tag"
    category = "on_page"
    description = "Page should have exactly one non-empty H1 tag"
    weight = 1.3
    tags = ["critical", "on_page", "headings"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        headings = data.get("headings", {})
        h1_tags = headings.get("h1", [])
        h1_count = len(h1_tags) if h1_tags else 0
        basic = data.get("basic", {})
        title = basic.get("title", "")
        
        if h1_count == 0:
            return [self._create_result(
                passed=False,
                message="Missing H1 tag",
                severity=Severity.CRITICAL,
                score_impact=-10,
                recommendation="Add a single <h1> tag containing your primary keyword",
            )]
        
        # Check for empty H1s
        empty_h1s = sum(1 for h in h1_tags if not h or not h.strip())
        if empty_h1s > 0:
            return [self._create_result(
                passed=False,
                message=f"Found {h1_count} H1 tags, including {empty_h1s} empty",
                severity=Severity.WARNING,
                score_impact=-5,
                recommendation="Ensure H1 tags contain descriptive text",
                data={"h1_count": h1_count, "empty_h1s": empty_h1s, "h1_tags": h1_tags[:3]},
            )]
        
        if h1_count > 1:
            return [self._create_result(
                passed=False,
                message=f"Multiple H1 tags found ({h1_count})",
                severity=Severity.WARNING,
                score_impact=-5,
                recommendation="Use only one H1 tag per page for better SEO",
                data={"h1_count": h1_count, "h1_tags": h1_tags[:3]},
            )]
        
        h1_text = h1_tags[0] if h1_tags else ""
        h1_length = len(h1_text)
        impacts = 0
        details = {"h1_count": 1, "h1_text": h1_text, "h1_length": h1_length}
        
        # Length check
        if h1_length > 100:
            impacts -= 2
            details["length_warning"] = True
        
        # H1/title consistency
        if title and h1_text:
            title_words = set(title.lower().split()[:5])
            h1_words = set(h1_text.lower().split()[:5])
            overlap = title_words & h1_words
            details["title_h1_overlap"] = len(overlap) / len(title_words) if title_words else 0
            if len(overlap) == 0:
                impacts -= 1
                details["consistency_warning"] = True
        
        if impacts == 0:
            return [self._create_result(
                passed=True,
                message="Has exactly one H1 tag",
                severity=Severity.PASSED,
                score_impact=0,
                data=details,
            )]
        
        return [self._create_result(
            passed=False,
            message=f"H1 tag issues detected (length={h1_length}, consistency issues)",
            severity=Severity.WARNING,
            score_impact=impacts,
            recommendation="Use one concise H1 tag that aligns with the page title",
            data=details,
        )]


class HeadingHierarchyRule(BaseRule):
    """Check heading hierarchy (H1 → H2 → H3)."""
    rule_id = "on_page_004"
    name = "Heading Hierarchy"
    category = "on_page"
    description = "Headings should follow logical hierarchy"
    weight = 1.0
    tags = ["warning", "on_page", "headings"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        headings = data.get("headings", {})
        heading_stats = headings.get("heading_stats", {})
        
        h1_count = len(headings.get("h1", []))
        h2_count = len(headings.get("h2", []))
        h3_count = len(headings.get("h3", []))
        h4_count = len(headings.get("h4", []))
        h5_count = len(headings.get("h5", []))
        h6_count = len(headings.get("h6", []))
        total_headings = heading_stats.get("heading_count", h1_count + h2_count + h3_count + h4_count + h5_count + h6_count)
        
        issues = []
        impacts = 0
        
        if h1_count == 0:
            issues.append("Missing H1")
            impacts -= 3
        
        if h2_count == 0 and h3_count > 0:
            issues.append("H3 used without H2")
            impacts -= 2
        
        if not heading_stats.get("is_sequential", True):
            issues.append("Heading levels are not sequential")
            impacts -= 2
        
        # Excessive headings
        if total_headings > 20:
            issues.append("Excessive headings")
            impacts -= 2
        elif h2_count > 10:
            issues.append("Too many H2 headings")
            impacts -= 1
        
        # Empty headings
        all_headings = []
        for level in range(1, 7):
            all_headings.extend(headings.get(f"h{level}", []))
        empty_headings = sum(1 for h in all_headings if not h or not h.strip())
        if empty_headings > 0:
            issues.append(f"{empty_headings} empty headings")
            impacts -= 1
        
        # Duplicate headings
        seen = set()
        duplicates = 0
        for h in all_headings:
            h_norm = h.strip().lower()
            if h_norm in seen:
                duplicates += 1
            seen.add(h_norm)
        if duplicates > 0:
            issues.append(f"{duplicates} duplicate headings")
            impacts -= 1
        
        # Heading length warnings
        long_headings = sum(1 for h in all_headings if len(h) > 100)
        if long_headings > 0:
            issues.append(f"{long_headings} headings longer than 100 characters")
            impacts -= 1
        
        if not issues:
            return [self._create_result(
                passed=True,
                message="Heading hierarchy is logical",
                severity=Severity.PASSED,
                score_impact=0,
                data={"h1": h1_count, "h2": h2_count, "h3": h3_count, "total": total_headings},
            )]
        
        return [self._create_result(
            passed=False,
            message=f"Heading hierarchy issues: {', '.join(issues)}",
            severity=Severity.WARNING,
            score_impact=impacts,
            recommendation="Organize headings in logical hierarchy (H1 → H2 → H3)",
            data={"h1": h1_count, "h2": h2_count, "h3": h3_count, "issues": issues, "total": total_headings},
        )]


class MetaKeywordsRule(BaseRule):
    """Check meta keywords (less important but still checked)."""
    rule_id = "on_page_005"
    name = "Meta Keywords"
    category = "on_page"
    description = "Check for meta keywords tag"
    weight = 0.5
    tags = ["info", "on_page", "meta"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        basic = data.get("basic", {})
        meta_keywords = basic.get("meta_keywords", [])
        
        if meta_keywords:
            return [self._create_result(
                passed=True,
                message=f"Meta keywords present ({len(meta_keywords)} keywords)",
                severity=Severity.INFO,
                score_impact=0,
            )]
        
        return [self._create_result(
            passed=True,
            message="Meta keywords not present (not critical for modern SEO)",
            severity=Severity.INFO,
            score_impact=0,
            recommendation="Meta keywords are deprecated but can be added if desired",
        )]


class CanonicalUrlRule(BaseRule):
    """Check canonical URL tag."""
    rule_id = "on_page_006"
    name = "Canonical URL"
    category = "on_page"
    description = "Page should have canonical URL to avoid duplicate content"
    weight = 1.1
    tags = ["critical", "on_page", "duplicate_content"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        seo = data.get("seo", {})
        canonical = seo.get("canonical_url", "")
        url_info = data.get("url", {})
        current_url = url_info.get("url", "") or url_info.get("normalized_url", "")
        
        if not canonical:
            return [self._create_result(
                passed=False,
                message="Missing canonical URL tag",
                severity=Severity.WARNING,
                score_impact=-5,
                recommendation="Add <link rel='canonical' href='...'> to prevent duplicate content issues",
            )]
        
        impacts = 0
        details = {"canonical_url": canonical}
        
        # Check if canonical is absolute
        if canonical.startswith("//") or (not canonical.startswith("http") and "//" not in canonical):
            impacts -= 2
            details["relative_canonical"] = True
        
        # Check self-referencing canonical
        if canonical == current_url:
            details["self_referencing"] = True
        
        # Check for common issues
        if "noindex" in canonical.lower():
            impacts -= 3
            details["noindex_in_canonical"] = True
        
        if impacts == 0:
            return [self._create_result(
                passed=True,
                message=f"Canonical URL is set: {canonical}",
                severity=Severity.PASSED,
                score_impact=0,
                data=details,
            )]
        
        return [self._create_result(
            passed=False,
            message=f"Canonical URL has issues: {canonical}",
            severity=Severity.WARNING,
            score_impact=impacts,
            recommendation="Ensure canonical URL is absolute and points to the preferred version",
            data=details,
        )]


class RobotsMetaRule(BaseRule):
    """Check robots meta tag."""
    rule_id = "on_page_007"
    name = "Robots Meta Tag"
    category = "on_page"
    description = "Check robots meta directives"
    weight = 1.0
    tags = ["warning", "on_page", "indexing"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        seo = data.get("seo", {})
        robots_meta = seo.get("robots_meta", "")
        x_robots = seo.get("x_robots_tag", "")
        
        robots_value = robots_meta or x_robots
        
        if not robots_value:
            return [self._create_result(
                passed=True,
                message="No robots restrictions (page will be indexed)",
                severity=Severity.PASSED,
                score_impact=0,
            )]
        
        robots_lower = robots_value.lower()
        if "noindex" in robots_lower:
            return [self._create_result(
                passed=False,
                message=f"Page is set to noindex: {robots_value}",
                severity=Severity.CRITICAL,
                score_impact=-20,
                recommendation="Remove noindex directive if page should be indexed",
                data={"robots_meta": robots_meta, "x_robots_tag": x_robots},
            )]
        
        if "nofollow" in robots_lower:
            return [self._create_result(
                passed=False,
                message=f"Links will not be followed: {robots_value}",
                severity=Severity.WARNING,
                score_impact=-5,
                recommendation="Remove nofollow if links should be crawled",
                data={"robots_meta": robots_meta, "x_robots_tag": x_robots},
            )]
        
        return [self._create_result(
            passed=True,
            message=f"Robots meta: {robots_value}",
            severity=Severity.PASSED,
            score_impact=0,
            data={"robots_meta": robots_meta, "x_robots_tag": x_robots},
        )]


class OpenGraphRule(BaseRule):
    """Check Open Graph tags for social sharing."""
    rule_id = "on_page_008"
    name = "Open Graph Tags"
    category = "on_page"
    description = "Check for Open Graph meta tags"
    weight = 0.8
    tags = ["info", "on_page", "social"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        social = data.get("social", {})
        og = social.get("open_graph", {})
        og_tags = og.get("tags", {})
        
        required = ["og:title", "og:description", "og:image", "og:url"]
        missing = [tag for tag in required if tag not in og_tags]
        
        if not missing:
            return [self._create_result(
                passed=True,
                message=f"All required Open Graph tags present ({len(og_tags)} total)",
                severity=Severity.PASSED,
                score_impact=0,
                data={"og_tags": list(og_tags.keys())},
            )]
        
        impact = -len(missing) * 2
        return [self._create_result(
            passed=False,
            message=f"Missing Open Graph tags: {', '.join(missing)}",
            severity=Severity.WARNING,
            score_impact=impact,
            recommendation=f"Add missing OG tags: {', '.join(missing)}",
            data={"missing": missing, "present": list(og_tags.keys())},
        )]


class TwitterCardsRule(BaseRule):
    """Check Twitter Card tags."""
    rule_id = "on_page_009"
    name = "Twitter Cards"
    category = "on_page"
    description = "Check for Twitter Card meta tags"
    weight = 0.6
    tags = ["info", "on_page", "social"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        social = data.get("social", {})
        twitter = social.get("twitter_cards", {})
        twitter_tags = twitter.get("tags", {})
        
        if not twitter_tags:
            return [self._create_result(
                passed=True,
                message="No Twitter Card tags (optional)",
                severity=Severity.INFO,
                score_impact=0,
                recommendation="Consider adding Twitter Card tags for better social sharing",
            )]
        
        required = ["twitter:card", "twitter:title", "twitter:description"]
        missing = [tag for tag in required if tag not in twitter_tags]
        
        if not missing:
            return [self._create_result(
                passed=True,
                message="Twitter Card tags present",
                severity=Severity.PASSED,
                score_impact=0,
            )]
        
        return [self._create_result(
            passed=False,
            message=f"Incomplete Twitter Card tags. Missing: {', '.join(missing)}",
            severity=Severity.INFO,
            score_impact=-1,
            recommendation=f"Add missing Twitter tags: {', '.join(missing)}",
        )]