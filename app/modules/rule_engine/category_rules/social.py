"""
Social Media and Sharing Rules.
"""
from typing import Any, Dict, List

from app.modules.scorer.services.base_rule import BaseRule
from app.modules.rule_engine.models.rule_result import RuleResult, Severity


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
