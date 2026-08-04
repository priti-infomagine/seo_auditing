"""
On-Page SEO Rules.
"""
from typing import Any, Dict, List

from app.services.scorer.base_rule import BaseRule
from app.models.scorer_models.rule_result import RuleResult, Severity


class TitleTagRule(BaseRule):
    """Check title tag presence and optimal length."""
    rule_id = "on_page_001"
    name = "Title Tag"
    category = "on_page"
    description = "Page must have a title tag with optimal length (30-60 chars)"
    weight = 1.5
    tags = ["critical", "on_page", "title"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        basic = data.get("basic", {})
        title = basic.get("title", "")
        title_length = basic.get("title_length", 0)
        
        if not title:
            return [self._create_result(
                passed=False,
                message="Missing page title tag",
                severity=Severity.CRITICAL,
                score_impact=-15,
                recommendation="Add a descriptive <title> tag (30-60 characters)",
            )]
        
        if 30 <= title_length <= 60:
            return [self._create_result(
                passed=True,
                message=f"Title length is optimal ({title_length} characters)",
                severity=Severity.PASSED,
                score_impact=0,
            )]
        
        impact = -5
        msg = f"Title length is {title_length} characters (recommended: 30-60)"
        if title_length < 30:
            msg += " - too short"
        else:
            msg += " - too long"
        
        return [self._create_result(
            passed=False,
            message=msg,
            severity=Severity.WARNING,
            score_impact=impact,
            recommendation="Adjust title length to 30-60 characters for optimal SERP display",
        )]


class MetaDescriptionRule(BaseRule):
    """Check meta description presence and optimal length."""
    rule_id = "on_page_002"
    name = "Meta Description"
    category = "on_page"
    description = "Page must have meta description with optimal length (150-160 chars)"
    weight = 1.2
    tags = ["critical", "on_page", "meta"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        basic = data.get("basic", {})
        meta_desc = basic.get("meta_description", "")
        meta_desc_length = basic.get("meta_description_length", 0)
        
        if not meta_desc:
            return [self._create_result(
                passed=False,
                message="Missing meta description",
                severity=Severity.CRITICAL,
                score_impact=-12,
                recommendation="Add a compelling meta description (150-160 characters)",
            )]
        
        if 150 <= meta_desc_length <= 160:
            return [self._create_result(
                passed=True,
                message=f"Meta description length is optimal ({meta_desc_length} characters)",
                severity=Severity.PASSED,
                score_impact=0,
            )]
        
        impact = -4
        msg = f"Meta description length is {meta_desc_length} characters (recommended: 150-160)"
        
        return [self._create_result(
            passed=False,
            message=msg,
            severity=Severity.WARNING,
            score_impact=impact,
            recommendation="Adjust meta description to 150-160 characters for optimal SERP display",
        )]


class H1TagRule(BaseRule):
    """Check H1 tag presence and count."""
    rule_id = "on_page_003"
    name = "H1 Tag"
    category = "on_page"
    description = "Page should have exactly one H1 tag"
    weight = 1.3
    tags = ["critical", "on_page", "headings"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        headings = data.get("headings", {})
        h1_tags = headings.get("h1", [])
        h1_count = len(h1_tags) if h1_tags else 0
        
        if h1_count == 0:
            return [self._create_result(
                passed=False,
                message="Missing H1 tag",
                severity=Severity.CRITICAL,
                score_impact=-10,
                recommendation="Add a single <h1> tag containing your primary keyword",
            )]
        
        if h1_count == 1:
            return [self._create_result(
                passed=True,
                message="Has exactly one H1 tag",
                severity=Severity.PASSED,
                score_impact=0,
            )]
        
        return [self._create_result(
            passed=False,
            message=f"Multiple H1 tags found ({h1_count})",
            severity=Severity.WARNING,
            score_impact=-5,
            recommendation="Use only one H1 tag per page for better SEO",
            data={"h1_count": h1_count, "h1_tags": h1_tags[:3]},
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
        
        issues = []
        impact = 0
        
        if h1_count == 0:
            issues.append("Missing H1")
            impact -= 3
        
        if h2_count == 0 and h3_count > 0:
            issues.append("H3 used without H2")
            impact -= 2
        
        if not heading_stats.get("is_sequential", True):
            issues.append("Heading levels are not sequential")
            impact -= 2
        
        if not issues:
            return [self._create_result(
                passed=True,
                message="Heading hierarchy is logical",
                severity=Severity.PASSED,
                score_impact=0,
                data={"h1": h1_count, "h2": h2_count, "h3": h3_count},
            )]
        
        return [self._create_result(
            passed=False,
            message=f"Heading hierarchy issues: {', '.join(issues)}",
            severity=Severity.WARNING,
            score_impact=impact,
            recommendation="Organize headings in logical hierarchy (H1 → H2 → H3)",
            data={"h1": h1_count, "h2": h2_count, "h3": h3_count, "issues": issues},
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
        
        if canonical:
            return [self._create_result(
                passed=True,
                message=f"Canonical URL is set: {canonical}",
                severity=Severity.PASSED,
                score_impact=0,
                data={"canonical_url": canonical},
            )]
        
        return [self._create_result(
            passed=False,
            message="Missing canonical URL tag",
            severity=Severity.WARNING,
            score_impact=-5,
            recommendation="Add <link rel='canonical' href='...'> to prevent duplicate content issues",
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