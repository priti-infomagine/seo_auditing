"""
Social Media and Sharing Rules.

This module contains all social media related SEO rules.
Rules are organized by their rule_id (social_001 through social_010).
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from app.modules.scorer.services.base_rule import BaseRule
from app.modules.rule_engine.models.rule_result import RuleResult, Severity
from app.modules.parser.services.image_validator import get_image_validator, ImageValidationResult


class OpenGraphTitleRule(BaseRule):
    """Check for og:title presence and quality."""
    rule_id = "social_001"
    name = "Open Graph Title"
    category = "social"
    description = "Checks for og:title meta tag presence and quality"
    weight = 0.8
    tags = ["warning", "social", "open_graph"]

    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        social = data.get("social", {})
        og = social.get("open_graph", {})
        og_tags = og.get("tags", {})

        og_title = og_tags.get("og:title", [""])[0] if og_tags.get("og:title") else ""

        if not og_title:
            return [self._create_result(
                passed=False,
                message="Missing og:title tag",
                severity=Severity.WARNING,
                score_impact=-3,
                recommendation="Add og:title meta tag for better social sharing previews",
            )]

        # Check length (recommended 40-60 chars)
        length = len(og_title)
        issues = []
        if length < 20:
            issues.append("too short (<20 chars)")
        elif length > 90:
            issues.append("too long (>90 chars, may truncate)")

        if issues:
            return [self._create_result(
                passed=False,
                message=f"og:title present but {', '.join(issues)} ({length} chars)",
                severity=Severity.INFO,
                score_impact=-1,
                recommendation="Optimize og:title to 40-60 characters for best display",
                data={"title": og_title, "length": length, "issues": issues},
            )]

        return [self._create_result(
            passed=True,
            message=f"og:title present and well-sized ({length} chars)",
            severity=Severity.PASSED,
            score_impact=0,
            data={"title": og_title, "length": length},
        )]


class OpenGraphDescriptionRule(BaseRule):
    """Check for og:description presence and quality."""
    rule_id = "social_002"
    name = "Open Graph Description"
    category = "social"
    description = "Checks for og:description meta tag presence and quality"
    weight = 0.7
    tags = ["warning", "social", "open_graph"]

    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        social = data.get("social", {})
        og = social.get("open_graph", {})
        og_tags = og.get("tags", {})

        og_desc = og_tags.get("og:description", [""])[0] if og_tags.get("og:description") else ""

        if not og_desc:
            return [self._create_result(
                passed=False,
                message="Missing og:description tag",
                severity=Severity.WARNING,
                score_impact=-3,
                recommendation="Add og:description meta tag for better social sharing previews",
            )]

        length = len(og_desc)
        issues = []
        if length < 50:
            issues.append("too short (<50 chars)")
        elif length > 300:
            issues.append("too long (>300 chars, may truncate)")

        if issues:
            return [self._create_result(
                passed=False,
                message=f"og:description present but {', '.join(issues)} ({length} chars)",
                severity=Severity.INFO,
                score_impact=-1,
                recommendation="Optimize og:description to 150-200 characters for best display",
                data={"description": og_desc, "length": length, "issues": issues},
            )]

        return [self._create_result(
            passed=True,
            message=f"og:description present and well-sized ({length} chars)",
            severity=Severity.PASSED,
            score_impact=0,
            data={"description": og_desc, "length": length},
        )]


class OpenGraphImageRule(BaseRule):
    """Check for valid og:image URL with HTTP validation."""
    rule_id = "social_003"
    name = "Open Graph Image"
    category = "social"
    description = "Checks for a valid og:image URL and validates accessibility"
    weight = 0.9
    tags = ["warning", "social", "open_graph", "images"]

    def __init__(self):
        super().__init__()
        self._validator = get_image_validator(timeout=5.0, enable_dimension_check=False)

    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        social = data.get("social", {})
        og = social.get("open_graph", {})
        og_tags = og.get("tags", {})
        twitter = social.get("twitter_cards", {})
        twitter_tags = twitter.get("tags", {})

        og_image = og_tags.get("og:image", [""])[0] if og_tags.get("og:image") else ""
        twitter_image = twitter_tags.get("twitter:image", [""])[0] if twitter_tags.get("twitter:image") else ""
        image_url = og_image or twitter_image

        if not image_url:
            return [self._create_result(
                passed=False,
                message="No social media image specified (missing og:image and twitter:image)",
                severity=Severity.WARNING,
                score_impact=-4,
                recommendation="Add og:image and twitter:image tags for better social sharing",
            )]

        # Validate image URL
        result = await self._validator.validate(image_url)

        if not result.accessible:
            return [self._create_result(
                passed=False,
                message=f"og:image URL is not accessible: {result.error or 'unknown error'}",
                severity=Severity.WARNING,
                score_impact=-3,
                recommendation="Ensure og:image URL returns 200 OK and serves a valid image",
                data={"image_url": image_url, "error": result.error, "final_url": result.final_url},
            )]

        # Check content type
        if result.content_type and not result.content_type.startswith("image/"):
            return [self._create_result(
                passed=False,
                message=f"og:image URL does not serve an image (content-type: {result.content_type})",
                severity=Severity.WARNING,
                score_impact=-2,
                recommendation="Ensure og:image URL serves a valid image file (JPEG, PNG, WebP, etc.)",
                data={"image_url": image_url, "content_type": result.content_type},
            )]

        return [self._create_result(
            passed=True,
            message="og:image URL is valid and accessible",
            severity=Severity.PASSED,
            score_impact=0,
            data={
                "image_url": image_url,
                "content_type": result.content_type,
                "content_length": result.content_length,
                "final_url": result.final_url,
            },
        )]


class OpenGraphImageDimensionsRule(BaseRule):
    """Check og:image dimensions (recommended 1200x630)."""
    rule_id = "social_004"
    name = "Open Graph Image Dimensions"
    category = "social"
    description = "Checks whether the social preview image has appropriate dimensions"
    weight = 0.6
    tags = ["info", "social", "open_graph", "images"]

    def __init__(self):
        super().__init__()
        self._validator = get_image_validator(timeout=5.0, enable_dimension_check=True)

    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        social = data.get("social", {})
        og = social.get("open_graph", {})
        og_tags = og.get("tags", {})
        twitter = social.get("twitter_cards", {})
        twitter_tags = twitter.get("tags", {})

        og_image = og_tags.get("og:image", [""])[0] if og_tags.get("og:image") else ""
        twitter_image = twitter_tags.get("twitter:image", [""])[0] if twitter_tags.get("twitter:image") else ""
        image_url = og_image or twitter_image

        if not image_url:
            return [self._create_result(
                passed=False,
                message="No social media image to check dimensions",
                severity=Severity.INFO,
                score_impact=0,
                recommendation="Add og:image to enable dimension checking",
            )]

        # Validate image and get dimensions
        result = await self._validator.validate(image_url)

        if not result.accessible:
            return [self._create_result(
                passed=False,
                message=f"Cannot check dimensions: image not accessible ({result.error})",
                severity=Severity.INFO,
                score_impact=0,
                recommendation="Fix image accessibility first",
                data={"image_url": image_url, "error": result.error},
            )]

        # Check dimensions
        dim_check = self._validator.check_dimensions(result)

        if dim_check["meets_recommended"]:
            return [self._create_result(
                passed=True,
                message=f"Image dimensions meet recommendations ({result.width}x{result.height})",
                severity=Severity.PASSED,
                score_impact=0,
                data={
                    "image_url": image_url,
                    "width": result.width,
                    "height": result.height,
                    "aspect_ratio": dim_check["aspect_ratio"],
                    "meets_recommended": True,
                    "meets_minimum": True,
                },
            )]

        if dim_check["meets_minimum"]:
            return [self._create_result(
                passed=True,
                message=f"Image meets minimum dimensions but not recommended ({result.width}x{result.height})",
                severity=Severity.INFO,
                score_impact=-1,
                recommendation=f"Consider using 1200x630 for optimal social previews. Current: {result.width}x{result.height}",
                data={
                    "image_url": image_url,
                    "width": result.width,
                    "height": result.height,
                    "aspect_ratio": dim_check["aspect_ratio"],
                    "meets_recommended": False,
                    "meets_minimum": True,
                    "issues": dim_check["issues"],
                },
            )]

        return [self._create_result(
            passed=False,
            message=f"Image below minimum dimensions ({result.width}x{result.height}, min 200x200)",
            severity=Severity.WARNING,
            score_impact=-2,
            recommendation=f"Use images at least 200x200, recommended 1200x630. Current: {result.width}x{result.height}",
            data={
                "image_url": image_url,
                "width": result.width,
                "height": result.height,
                "aspect_ratio": dim_check["aspect_ratio"],
                "meets_recommended": False,
                "meets_minimum": False,
                "issues": dim_check["issues"],
            },
        )]


class TwitterCardMetadataRule(BaseRule):
    """Check for twitter:card and appropriate card type."""
    rule_id = "social_005"
    name = "Twitter Card Metadata"
    category = "social"
    description = "Checks for twitter:card and an appropriate card type"
    weight = 0.7
    tags = ["info", "social", "twitter"]

    VALID_CARD_TYPES = {"summary", "summary_large_image", "app", "player"}

    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        social = data.get("social", {})
        twitter = social.get("twitter_cards", {})
        twitter_tags = twitter.get("tags", {})

        if not twitter_tags:
            return [self._create_result(
                passed=False,
                message="No Twitter Card tags found",
                severity=Severity.INFO,
                score_impact=-1,
                recommendation="Add Twitter Card meta tags for better sharing on X/Twitter",
            )]

        card_type = twitter_tags.get("twitter:card", [""])[0] if twitter_tags.get("twitter:card") else ""

        if not card_type:
            return [self._create_result(
                passed=False,
                message="Twitter Card tags present but missing twitter:card",
                severity=Severity.WARNING,
                score_impact=-2,
                recommendation="Add twitter:card meta tag with valid type (summary, summary_large_image, app, player)",
            )]

        card_type_lower = card_type.lower().strip()
        issues = []
        if card_type_lower not in self.VALID_CARD_TYPES:
            issues.append(f"invalid card type '{card_type}'")

        # Check required fields per card type
        if card_type_lower in ("summary", "summary_large_image"):
            required = ["twitter:title", "twitter:description", "twitter:image"]
            for field in required:
                if not twitter_tags.get(field):
                    issues.append(f"missing {field}")

        if issues:
            return [self._create_result(
                passed=False,
                message=f"Twitter Card issues: {', '.join(issues)}",
                severity=Severity.WARNING if "invalid" in str(issues) else Severity.INFO,
                score_impact=-2 if "invalid" in str(issues) else -1,
                recommendation="Fix Twitter Card: use valid card type and include required fields",
                data={"card_type": card_type, "issues": issues, "tags": list(twitter_tags.keys())},
            )]

        return [self._create_result(
            passed=True,
            message=f"Twitter Card valid: {card_type}",
            severity=Severity.PASSED,
            score_impact=0,
            data={"card_type": card_type, "tags": list(twitter_tags.keys())},
        )]


class OpenGraphUrlRule(BaseRule):
    """Check for valid og:url."""
    rule_id = "social_006"
    name = "Open Graph URL"
    category = "social"
    description = "Checks for a valid og:url"
    weight = 0.5
    tags = ["info", "social", "open_graph"]

    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        social = data.get("social", {})
        og = social.get("open_graph", {})
        og_tags = og.get("tags", {})

        og_url = og_tags.get("og:url", [""])[0] if og_tags.get("og:url") else ""

        if not og_url:
            return [self._create_result(
                passed=False,
                message="Missing og:url tag",
                severity=Severity.INFO,
                score_impact=-1,
                recommendation="Add og:url meta tag with the canonical URL of the page",
            )]

        # Validate URL format
        try:
            parsed = urlparse(og_url)
            if not parsed.scheme or not parsed.netloc:
                raise ValueError("Invalid URL")
            if parsed.scheme not in ("http", "https"):
                raise ValueError("Non-HTTP scheme")
        except Exception:
            return [self._create_result(
                passed=False,
                message=f"og:url is not a valid HTTP/HTTPS URL: {og_url}",
                severity=Severity.WARNING,
                score_impact=-2,
                recommendation="Ensure og:url is a valid absolute HTTP/HTTPS URL",
                data={"og_url": og_url},
            )]

        return [self._create_result(
            passed=True,
            message="og:url is present and valid",
            severity=Severity.PASSED,
            score_impact=0,
            data={"og_url": og_url},
        )]


class OpenGraphCanonicalConsistencyRule(BaseRule):
    """Check whether og:url matches the canonical URL."""
    rule_id = "social_007"
    name = "Open Graph Canonical Consistency"
    category = "social"
    description = "Checks whether og:url matches the canonical URL"
    weight = 0.8
    tags = ["warning", "social", "open_graph", "canonical"]

    @staticmethod
    def _normalize_url(url: str) -> str:
        """Normalize URL for comparison."""
        try:
            parsed = urlparse(url.strip())
            # Lowercase scheme and host
            scheme = parsed.scheme.lower()
            netloc = parsed.netloc.lower()
            # Remove default ports
            if (scheme == "http" and netloc.endswith(":80")) or \
               (scheme == "https" and netloc.endswith(":443")):
                netloc = netloc.rsplit(":", 1)[0]
            # Remove trailing slash from path (except root)
            path = parsed.path
            if path.endswith("/") and len(path) > 1:
                path = path[:-1]
            # Reconstruct
            normalized = f"{scheme}://{netloc}{path}"
            if parsed.query:
                normalized += f"?{parsed.query}"
            return normalized
        except Exception:
            return url.strip().lower()

    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        social = data.get("social", {})
        og = social.get("open_graph", {})
        og_tags = og.get("tags", {})
        seo = data.get("seo", {})

        og_url = og_tags.get("og:url", [""])[0] if og_tags.get("og:url") else ""
        canonical_url = seo.get("canonical_url", "")

        if not og_url:
            return [self._create_result(
                passed=False,
                message="Cannot check consistency: og:url missing",
                severity=Severity.WARNING,
                score_impact=-2,
                recommendation="Add og:url to enable canonical consistency check",
            )]

        if not canonical_url:
            return [self._create_result(
                passed=False,
                message="Cannot check consistency: canonical URL missing",
                severity=Severity.INFO,
                score_impact=-1,
                recommendation="Add canonical URL to enable consistency check",
            )]

        og_normalized = self._normalize_url(og_url)
        canonical_normalized = self._normalize_url(canonical_url)

        if og_normalized == canonical_normalized:
            return [self._create_result(
                passed=True,
                message="og:url matches canonical URL",
                severity=Severity.PASSED,
                score_impact=0,
                data={"og_url": og_url, "canonical_url": canonical_url},
            )]

        # Check if they differ only by www
        og_no_www = og_normalized.replace("://www.", "://")
        canonical_no_www = canonical_normalized.replace("://www.", "://")
        if og_no_www == canonical_no_www:
            return [self._create_result(
                passed=True,
                message="og:url matches canonical URL (www difference only)",
                severity=Severity.PASSED,
                score_impact=0,
                data={"og_url": og_url, "canonical_url": canonical_url, "www_difference": True},
            )]

        return [self._create_result(
            passed=False,
            message=f"og:url ({og_url}) does not match canonical URL ({canonical_url})",
            severity=Severity.WARNING,
            score_impact=-3,
            recommendation="Ensure og:url matches the canonical URL to avoid social sharing confusion",
            data={"og_url": og_url, "canonical_url": canonical_url},
        )]


class SocialSharingIntegrationRule(BaseRule):
    """Check whether social sharing options are available on the page."""
    rule_id = "social_008"
    name = "Social Sharing Integration"
    category = "social"
    description = "Checks whether social sharing options are available on the page"
    weight = 0.4
    tags = ["info", "social", "sharing"]

    # Note: This is a product-level recommendation, not a universal SEO requirement
    # Per spec: "Do not fail a page solely because it lacks social sharing buttons"

    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        social = data.get("social", {})
        sharing_buttons = social.get("sharing_buttons", [])

        if not sharing_buttons:
            return [self._create_result(
                passed=True,  # Not a failure per spec
                message="No social sharing buttons detected (optional, product-level decision)",
                severity=Severity.INFO,
                score_impact=0,
                recommendation="Consider adding social sharing buttons for better content distribution",
                data={"sharing_buttons": [], "count": 0},
            )]

        platforms = [btn.get("platform", "") for btn in sharing_buttons if isinstance(btn, dict)]
        unique_platforms = list(set(platforms))

        return [self._create_result(
            passed=True,
            message=f"Social sharing buttons found: {', '.join(unique_platforms)}",
            severity=Severity.PASSED,
            score_impact=0,
            data={
                "sharing_buttons": sharing_buttons,
                "count": len(sharing_buttons),
                "platforms": unique_platforms,
            },
        )]


class SocialProfileLinksRule(BaseRule):
    """Check for links to the website's official social media profiles."""
    rule_id = "social_009"
    name = "Social Profile Links"
    category = "social"
    description = "Checks for links to the website's official social media profiles"
    weight = 0.5
    tags = ["info", "social", "links"]

    COMMON_PLATFORMS = ["facebook", "twitter", "linkedin", "instagram", "youtube", "pinterest", "tiktok", "github"]

    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        social = data.get("social", {})
        social_links = social.get("social_links", [])

        if not social_links:
            return [self._create_result(
                passed=False,
                message="No social media profile links found",
                severity=Severity.INFO,
                score_impact=-1,
                recommendation="Add links to your official social media profiles",
            )]

        platforms = [link.get("platform", "").lower() for link in social_links if isinstance(link, dict)]
        present_platforms = [p for p in platforms if p in self.COMMON_PLATFORMS]

        if not present_platforms:
            return [self._create_result(
                passed=False,
                message="Social links found but none on recognized platforms",
                severity=Severity.INFO,
                score_impact=0,
                recommendation="Ensure social links point to recognized platforms (Facebook, Twitter/X, LinkedIn, Instagram, YouTube, etc.)",
                data={"platforms": platforms, "total_links": len(social_links)},
            )]

        return [self._create_result(
            passed=True,
            message=f"Social media profile links found: {', '.join(set(present_platforms))}",
            severity=Severity.PASSED,
            score_impact=0,
            data={"platforms": list(set(present_platforms)), "total_links": len(social_links)},
        )]


class FacebookDomainRule(BaseRule):
    """Check for Facebook domain verification."""
    rule_id = "social_010"
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
                recommendation="Add fb:app_id or fb:admins for Facebook Insights and domain verification",
            )]

        return [self._create_result(
            passed=True,
            message="Facebook domain verification present",
            severity=Severity.PASSED,
            score_impact=0,
            data={
                "has_fb_app_id": has_fb_app_id,
                "has_fb_admins": has_fb_admins,
                "fb_app_id": og_tags.get("fb:app_id", [""])[0] if has_fb_app_id else None,
            },
        )]