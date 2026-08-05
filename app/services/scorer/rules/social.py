"""
Social Media and Sharing Rules.
"""
from typing import Any, Dict, List

from app.services.scorer.base_rule import BaseRule
from app.models.scorer_models.rule_result import RuleResult, Severity


class OpenGraphRule(BaseRule):
    """Check Open Graph tags."""
    rule_id = "social_001"
    name = "Open Graph Tags"
    category = "social"
    description = "Check for Open Graph meta tags for social sharing"
    weight = 0.8
    tags = ["info", "social", "sharing"]
    
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
    rule_id = "social_002"
    name = "Twitter Cards"
    category = "social"
    description = "Check for Twitter Card meta tags"
    weight = 0.6
    tags = ["info", "social", "twitter"]
    
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


class SocialMediaLinksRule(BaseRule):
    """Check for social media profile links."""
    rule_id = "social_003"
    name = "Social Media Links"
    category = "social"
    description = "Check for links to social media profiles"
    weight = 0.5
    tags = ["info", "social", "links"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        social = data.get("social", {})
        social_links = social.get("social_links", {})
        links = social_links.get("links", [])
        
        if not links:
            return [self._create_result(
                passed=False,
                message="No social media links found",
                severity=Severity.INFO,
                score_impact=-1,
                recommendation="Add links to your social media profiles",
            )]
        
        platforms = [link.get("platform", "").lower() for link in links]
        common_platforms = ["facebook", "twitter", "linkedin", "instagram", "youtube"]
        present_platforms = [p for p in platforms if p in common_platforms]
        
        return [self._create_result(
            passed=True,
            message=f"Social media links found: {', '.join(set(present_platforms))}",
            severity=Severity.PASSED,
            score_impact=0,
            data={"platforms": list(set(present_platforms)), "total_links": len(links)},
        )]


class FacebookDomainRule(BaseRule):
    """Check for Facebook domain verification."""
    rule_id = "social_004"
    name = "Facebook Domain Verification"
    category = "social"
    description = "Check for Facebook domain verification meta tag"
    weight = 0.4
    tags = ["info", "social", "facebook"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        social = data.get("social", {})
        og = social.get("open_graph", {})
        og_tags = og.get("tags", {})
        
        has_fb_app_id = "fb:app_id" in og_tags
        has_fb_admins = "fb:admins" in og_tags
        
        if not has_fb_app_id and not has_fb_admins:
            return [self._create_result(
                passed=False,
                message="No Facebook App ID or admins meta tag",
                severity=Severity.INFO,
                score_impact=-1,
                recommendation="Add fb:app_id or fb:admins for Facebook Insights",
            )]
        
        return [self._create_result(
            passed=True,
            message="Facebook domain verification present",
            severity=Severity.PASSED,
            score_impact=0,
        )]


class SocialImageRule(BaseRule):
    """Check social media image."""
    rule_id = "social_005"
    name = "Social Media Image"
    category = "social"
    description = "Check for proper social sharing image"
    weight = 0.7
    tags = ["warning", "social", "images"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        social = data.get("social", {})
        og = social.get("open_graph", {})
        og_tags = og.get("tags", {})
        twitter = social.get("twitter_cards", {})
        twitter_tags = twitter.get("tags", {})
        
        og_image = og_tags.get("og:image", "")
        twitter_image = twitter_tags.get("twitter:image", "")
        image_url = og_image or twitter_image
        
        if not image_url:
            return [self._create_result(
                passed=False,
                message="No social media image specified",
                severity=Severity.WARNING,
                score_impact=-3,
                recommendation="Add og:image and twitter:image tags for better social sharing",
            )]
        
        return [self._create_result(
            passed=True,
            message="Social media image specified",
            severity=Severity.PASSED,
            score_impact=0,
            data={"image_url": image_url},
        )]