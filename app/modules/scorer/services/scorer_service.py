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
        try:
            logger.info("Starting SEO scoring...")
            
            # Prepare rule data: transforms parsed lists into summary dicts that rules expect
            rule_data = self._prepare_rule_data(parsed_data)
            
            # Run all rules
            rule_results = []
            for rule in self.rules:
                try:
                    results = await rule.evaluate(rule_data)
                    rule_results.extend(results)
                except Exception as e:
                    logger.error(f"Error running rule {rule.rule_id}: {e}")
                    # Create synthetic error result so the rule is visible in output
                    from app.modules.rule_engine.models.rule_result import RuleResult, Severity
                    error_result = RuleResult(
                        rule_id=rule.rule_id,
                        name=rule.name,
                        category=rule.category,
                        severity=Severity.ERROR,
                        passed=False,
                        score_impact=0,
                        message=f"Rule evaluation failed: {e}",
                        recommendation="Check rule implementation for data mismatch",
                        tags=rule.tags,
                    )
                    rule_results.append(error_result)
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
        except Exception as ex:
            logger.error(f"ScorerService.score_parsed_data: unhandled error: {ex}", exc_info=True)
            raise
    
    async def score_url(self, url: str, crawl_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Score a URL (requires crawl data).
        
        Args:
            url: URL to score
            crawl_data: Optional pre-fetched crawl data
            
        Returns:
            Complete SEO score report
        """
        try:
            if not crawl_data:
                raise ValueError("crawl_data is required for scoring")
            
            # Extract parsed data from crawl data
            # The parser service would normally populate a 'data' key
            parsed_data = crawl_data.get("data", crawl_data)
            
            return await self.score_parsed_data(parsed_data)
        except ValueError:
            raise
        except Exception as exc:
            logger.error(f"ScorerService.score_url: error for url={url}: {exc}", exc_info=True)
            raise
    
    def _prepare_rule_data(self, parsed_data):
        """Transform parsed_data into the dict structure that SEO rules expect."""
        from urllib.parse import urlparse
        data = {}
        metadata = parsed_data.get('metadata', {}) or {}
        basic = {'title': '', 'meta_description': '', 'canonical': '', 'robots_meta': '', 'language': '', 'charset': '', 'viewport': '', 'favicon': '', 'word_count': 0}
        for k in basic:
            basic[k] = metadata.get(k, basic[k])
        data['basic'] = basic
        data['seo'] = basic
        data['content'] = parsed_data.get('content', {}) or {}

        headings_list = parsed_data.get('headings', [])
        hd = {'h' + str(i): [] for i in range(1, 7)}
        hd['heading_stats'] = {'is_sequential': True, 'max_level': 0, 'heading_count': 0}
        for h in headings_list:
            if isinstance(h, dict):
                level = h.get('level', 0)
                text = h.get('text', '')
                if 1 <= level <= 6:
                    hd['h' + str(level)].append(text)
                hd['heading_stats']['heading_count'] += 1
                if level > hd['heading_stats']['max_level']:
                    hd['heading_stats']['max_level'] = level
        data['headings'] = hd

        links_list = parsed_data.get('links', [])
        ic = ec = nc = 0
        il = []
        el = []
        for link in links_list:
            if isinstance(link, dict):
                is_ext = link.get('link_type') == 'external' or link.get('is_external', False)
                if is_ext:
                    ec += 1
                    el.append(link)
                else:
                    ic += 1
                    il.append(link)
                if link.get('nofollow') or link.get('is_nofollow'):
                    nc += 1
        data['links'] = {'total_links': len(links_list), 'internal_count': ic, 'external_count': ec, 'nofollow_count': nc, 'internal_links': il, 'external_links': el}

        images_list = parsed_data.get('images', [])
        wa = 0
        ll = False
        sample = []
        for img in images_list:
            if isinstance(img, dict):
                alt = img.get('alt', '')
                if not alt or not alt.strip():
                    wa += 1
                if img.get('loading', '').strip().lower() == 'lazy':
                    ll = True
                if len(sample) < 20:
                    sample.append({'src': img.get('url', img.get('src', '')), 'alt': alt, 'title': img.get('title', ''), 'width': img.get('width', ''), 'height': img.get('height', ''), 'loading': img.get('loading', ''), 'srcset': img.get('srcset', ''), 'sizes': img.get('sizes', ''), 'file_size': 0})
        data['images'] = {'total_count': len(images_list), 'without_alt': wa, 'with_alt': len(images_list) - wa, 'lazy_loading': ll, 'sample': sample, 'has_alt_text': wa == 0}
        data['media'] = data['images']

        schemas_list = parsed_data.get('schemas', [])
        schema_markup = []
        for schema in schemas_list:
            if isinstance(schema, dict):
                parsed_val = schema.get('parsed', schema.get('raw', {}))
                if isinstance(parsed_val, dict):
                    schema_markup.append(parsed_val)
                else:
                    type_val = schema.get('types', [])
                    tn = type_val[0] if type_val else 'Unknown'
                    schema_markup.append({'@type': str(tn)})
            else:
                schema_markup.append({'@type': str(schema)})
        data['structured_data'] = {'schema_markup': schema_markup, 'schema_count': len(schema_markup)}

        data['social'] = parsed_data.get('social', {}) or {}
        crawler_data = parsed_data.get('crawler_data', {}) or {}
        rt = crawler_data.get('response_time_ms', 0)
        data['http'] = {'status_code': crawler_data.get('status_code', 0), 'content_type': crawler_data.get('content_type', ''), 'response_time': rt / 1000.0 if rt else 0.0, 'headers': crawler_data.get('headers', {})}
        document = parsed_data.get('document', {}) or {}
        url_str = document.get('url', '') or ''
        pu = urlparse(url_str) if url_str else None
        data['url'] = {'https': url_str.startswith('https://') if url_str else False, 'domain': pu.netloc if pu else '', 'path': pu.path if pu else '', 'query': pu.query if pu else ''}
        data['ssl'] = crawler_data.get('ssl', {}) or {}
        data['performance'] = {}
        data['javascript'] = {}
        data['security_headers'] = {}
        data['robots'] = {}
        data['sitemap'] = {}
        return data

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