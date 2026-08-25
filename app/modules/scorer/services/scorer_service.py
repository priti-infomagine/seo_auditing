"""
Scorer Service - Orchestrates all scoring rules and produces SEO score.
"""
from typing import Dict, Any, List, Optional
from app.modules.scorer.services.base_rule import BaseRule
from app.modules.scorer.services.score_calculator import ScoreCalculator
from app.modules.rule_engine.models.rule_result import RuleResult
from app.core.logger import logger


# Import all rule classes
from app.modules.rule_engine.category_rules.on_page import (
    TitleTagRule, MetaDescriptionRule, H1TagRule, HeadingHierarchyRule,
    MetaKeywordsRule, CanonicalUrlRule, RobotsMetaRule, OpenGraphRule, TwitterCardsRule
)
from app.modules.rule_engine.category_rules.technical import (
    SSL_CertificateRule, MobileViewportRule, LanguageDeclarationRule,
    CharsetRule, DoctypeRule, HtmlLangRule, SecurityHeadersRule,
    RobotsTxtRule, SitemapRule, StructuredDataRule
)
from app.modules.rule_engine.category_rules.content import (
    WordCountRule, ReadingTimeRule, ParagraphCountRule, TextHtmlRatioRule,
    KeywordInContentRule, DuplicateContentRule, ContentFreshnessRule
)
from app.modules.rule_engine.category_rules.links import (
    InternalLinksRule, ExternalLinksRule, BrokenLinksRule,
    AnchorTextRule, NofollowLinksRule
)
from app.modules.rule_engine.category_rules.images import (
    ImageAltTextRule, ImageSizeRule, LazyLoadingRule, ImageDimensionsRule,
    ResponsiveImagesRule, ImageFormatsRule
)
from app.modules.rule_engine.category_rules.schema import (
    SchemaMarkupRule, OrganizationSchemaRule, BreadcrumbSchemaRule,
    ArticleSchemaRule, ProductSchemaRule, JsonLdFormatRule
)
from app.modules.rule_engine.category_rules.social import (
    OpenGraphRule, TwitterCardsRule, SocialMediaLinksRule,
    FacebookDomainRule, SocialImageRule
)
from app.modules.rule_engine.category_rules.security import (
    HTTPSRule, MixedContentRule, SecurityHeadersRule, SSLCertificateRule,
    HSTSRule, XSSProtectionRule
)
from app.modules.rule_engine.category_rules.accessibility import (
    AltTextRule, LanguageRule, HeadingStructureRule, LinkTextRule,
    ColorContrastRule, KeyboardNavigationRule, ARIALabelsRule, FormLabelsRule
)
from app.modules.rule_engine.category_rules.performance import (
    ResponseTimeRule, HTMLSizeRule, MinificationRule, ResourceCountRule,
    CacheHeadersRule, CompressionRule, PageSizeRule, JavaScriptErrorsRule
)


class ScorerService:
    """
    Orchestrates SEO scoring by running all rules and calculating final score.
    """
    
    def __init__(self, custom_weights: Optional[Dict[str, float]] = None):
        """
        Initialize scorer service.
        
        Args:
            custom_weights: Optional custom weights for categories
        """
        self.score_calculator = ScoreCalculator(weights=custom_weights)
        self.rules = self._load_rules()
    
    def _load_rules(self) -> List[BaseRule]:
        """Load all scoring rules."""
        rules = [
            # On-Page (9 rules)
            TitleTagRule(), MetaDescriptionRule(), H1TagRule(),
            HeadingHierarchyRule(), MetaKeywordsRule(), CanonicalUrlRule(),
            RobotsMetaRule(), OpenGraphRule(), TwitterCardsRule(),
            
            # Technical (10 rules)
            SSLCertificateRule(), MobileViewportRule(), LanguageDeclarationRule(),
            CharsetRule(), DoctypeRule(), HtmlLangRule(),
            SecurityHeadersRule(), RobotsTxtRule(), SitemapRule(), StructuredDataRule(),
            
            # Content (7 rules)
            WordCountRule(), ReadingTimeRule(), ParagraphCountRule(),
            TextHtmlRatioRule(), KeywordInContentRule(), DuplicateContentRule(),
            ContentFreshnessRule(),
            
            # Links (5 rules)
            InternalLinksRule(), ExternalLinksRule(), BrokenLinksRule(),
            AnchorTextRule(), NofollowLinksRule(),
            
            # Images (6 rules)
            ImageAltTextRule(), ImageSizeRule(), LazyLoadingRule(),
            ImageDimensionsRule(), ResponsiveImagesRule(), ImageFormatsRule(),
            
            # Schema (6 rules)
            SchemaMarkupRule(), OrganizationSchemaRule(), BreadcrumbSchemaRule(),
            ArticleSchemaRule(), ProductSchemaRule(), JsonLdFormatRule(),
            
            # Social (5 rules)
            OpenGraphRule(), TwitterCardsRule(), SocialMediaLinksRule(),
            FacebookDomainRule(), SocialImageRule(),
            
            # Security (6 rules)
            HTTPSRule(), MixedContentRule(), SecurityHeadersRule(),
            SSL_CertificateRule(), HSTSRule(), XSSProtectionRule(),
            
            # Accessibility (8 rules)
            AltTextRule(), LanguageRule(), HeadingStructureRule(),
            LinkTextRule(), ColorContrastRule(), KeyboardNavigationRule(),
            ARIALabelsRule(), FormLabelsRule(),
            
            # Performance (8 rules)
            ResponseTimeRule(), HTMLSizeRule(), MinificationRule(),
            ResourceCountRule(), CacheHeadersRule(), CompressionRule(),
            PageSizeRule(), JavaScriptErrorsRule(),
        ]
        
        logger.info(f"Loaded {len(rules)} scoring rules")
        return rules
    
    async def score_parsed_data(self, parsed_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Score parsed data from the parser service.
        
        Args:
            parsed_data: Parsed SEO data (from parser service)
            
        Returns:
            Complete SEO score report
        """
        logger.info("Starting SEO scoring...")
        
        # Run all rules
        rule_results = []
        for rule in self.rules:
            try:
                results = await rule.evaluate(parsed_data)
                rule_results.extend(results)
            except Exception as e:
                logger.error(f"Error running rule {rule.rule_id}: {e}")
                continue
        
        logger.info(f"Completed {len(rule_results)} rule evaluations")
        
        # Calculate final score
        score_report = self.score_calculator.calculate_score(rule_results)
        
        # Add raw results for transparency
        score_report["rule_results"] = rule_results
        
        logger.info(
            f"SEO Score calculated: {score_report['overall_score']}/100 "
            f"(Grade {score_report['grade']})"
        )
        
        return score_report
    
    async def score_url(self, url: str, crawl_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Score a URL (requires crawl data).
        
        Args:
            url: URL to score
            crawl_data: Optional pre-fetched crawl data
            
        Returns:
            Complete SEO score report
        """
        if not crawl_data:
            raise ValueError("crawl_data is required for scoring")
        
        # Extract parsed data from crawl data
        # The parser service would normally populate a 'data' key
        parsed_data = crawl_data.get("data", crawl_data)
        
        return await self.score_parsed_data(parsed_data)
    
    def get_rule_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about loaded rules.
        
        Returns:
            Dictionary with rule statistics
        """
        categories = {}
        for rule in self.rules:
            cat = rule.category
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(rule.rule_id)
        
        return {
            "total_rules": len(self.rules),
            "categories": {
                cat: {"count": len(rules), "rules": rules}
                for cat, rules in categories.items()
            }
        }