"""
Schema / Structured Data Rules.
"""
from typing import Any, Dict, List

from app.modules.scorer.services.base_rule import BaseRule
from app.modules.rule_engine.models.rule_result import RuleResult, Severity


class SchemaMarkupRule(BaseRule):
    """Check for schema.org structured data."""
    rule_id = "schema_001"
    name = "Schema Markup"
    category = "schema"
    description = "Page should have structured data markup"
    weight = 1.0
    tags = ["warning", "schema", "rich_snippets"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        structured_data = data.get("structured_data", {})
        schema_markup = structured_data.get("schema_markup", [])
        
        if not schema_markup:
            return [self._create_result(
                passed=False,
                message="No structured data / schema markup found",
                severity=Severity.WARNING,
                score_impact=-5,
                recommendation="Add Schema.org markup to enable rich snippets in search results",
            )]
        
        # Check for common schema types
        schema_types = []
        for schema in schema_markup[:5]:
            schema_type = schema.get("@type") or schema.get("type", "Unknown")
            schema_types.append(schema_type)
        
        return [self._create_result(
            passed=True,
            message=f"Structured data found ({len(schema_markup)} items): {', '.join(schema_types[:3])}",
            severity=Severity.PASSED,
            score_impact=0,
            data={"schema_count": len(schema_markup), "types": schema_types},
        )]


class OrganizationSchemaRule(BaseRule):
    """Check for Organization schema."""
    rule_id = "schema_002"
    name = "Organization Schema"
    category = "schema"
    description = "Organization schema helps with knowledge panel"
    weight = 0.8
    tags = ["info", "schema", "branding"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        structured_data = data.get("structured_data", {})
        schema_markup = structured_data.get("schema_markup", [])
        
        if not schema_markup:
            return [self._create_result(
                passed=True,
                message="No schema markup to analyze",
                severity=Severity.INFO,
                score_impact=0,
            )]
        
        has_org = any(
            schema.get("@type", "").lower() in ["organization", "localbusiness", "corporation"]
            for schema in schema_markup
        )
        
        if has_org:
            return [self._create_result(
                passed=True,
                message="Organization schema found",
                severity=Severity.PASSED,
                score_impact=0,
            )]
        
        return [self._create_result(
            passed=False,
            message="No Organization schema found",
            severity=Severity.INFO,
            score_impact=-1,
            recommendation="Add Organization or LocalBusiness schema for brand visibility",
        )]


class BreadcrumbSchemaRule(BaseRule):
    """Check for breadcrumb schema."""
    rule_id = "schema_003"
    name = "Breadcrumb Schema"
    category = "schema"
    description = "Breadcrumb schema improves navigation display"
    weight = 0.7
    tags = ["info", "schema", "navigation"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        structured_data = data.get("structured_data", {})
        schema_markup = structured_data.get("schema_markup", [])
        
        if not schema_markup:
            return [self._create_result(
                passed=True,
                message="No schema markup to analyze",
                severity=Severity.INFO,
                score_impact=0,
            )]
        
        has_breadcrumb = any(
            "breadcrumb" in schema.get("@type", "").lower()
            for schema in schema_markup
        )
        
        if has_breadcrumb:
            return [self._create_result(
                passed=True,
                message="Breadcrumb schema found",
                severity=Severity.PASSED,
                score_impact=0,
            )]
        
        return [self._create_result(
            passed=False,
            message="No breadcrumb schema found",
            severity=Severity.INFO,
            score_impact=-1,
            recommendation="Add BreadcrumbList schema for better navigation display",
        )]


class ArticleSchemaRule(BaseRule):
    """Check for Article/NewsArticle schema."""
    rule_id = "schema_004"
    name = "Article Schema"
    category = "schema"
    description = "Article schema for content pages"
    weight = 0.7
    tags = ["info", "schema", "content"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        structured_data = data.get("structured_data", {})
        schema_markup = structured_data.get("schema_markup", [])
        
        if not schema_markup:
            return [self._create_result(
                passed=True,
                message="No schema markup to analyze",
                severity=Severity.INFO,
                score_impact=0,
            )]
        
        article_types = ["article", "newsarticle", "blogposting", "scholarlyarticle"]
        has_article = any(
            schema.get("@type", "").lower() in article_types
            for schema in schema_markup
        )
        
        if has_article:
            return [self._create_result(
                passed=True,
                message="Article schema found",
                severity=Severity.PASSED,
                score_impact=0,
            )]
        
        return [self._create_result(
            passed=False,
            message="No Article schema found",
            severity=Severity.INFO,
            score_impact=-1,
            recommendation="Add Article or BlogPosting schema for content pages",
        )]


class ProductSchemaRule(BaseRule):
    """Check for Product schema."""
    rule_id = "schema_005"
    name = "Product Schema"
    category = "schema"
    description = "Product schema for e-commerce pages"
    weight = 0.7
    tags = ["info", "schema", "ecommerce"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        structured_data = data.get("structured_data", {})
        schema_markup = structured_data.get("schema_markup", [])
        
        if not schema_markup:
            return [self._create_result(
                passed=True,
                message="No schema markup to analyze",
                severity=Severity.INFO,
                score_impact=0,
            )]
        
        has_product = any(
            schema.get("@type", "").lower() in ["product", "offer", "aggregateoffer"]
            for schema in schema_markup
        )
        
        if has_product:
            return [self._create_result(
                passed=True,
                message="Product schema found",
                severity=Severity.PASSED,
                score_impact=0,
            )]
        
        return [self._create_result(
            passed=False,
            message="No Product schema found",
            severity=Severity.INFO,
            score_impact=-1,
            recommendation="Add Product schema for e-commerce pages",
        )]


class JsonLdFormatRule(BaseRule):
    """Check that schema uses valid JSON-LD format."""
    rule_id = "schema_006"
    name = "JSON-LD Format"
    category = "schema"
    description = "Schema should use valid JSON-LD format (recommended by Google)"
    weight = 0.6
    tags = ["info", "schema", "format"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        structured_data = data.get("structured_data", {})
        schema_markup = structured_data.get("schema_markup", [])
        formats = structured_data.get("formats", [])
        
        if not schema_markup:
            return [self._create_result(
                passed=True,
                message="No schema markup to analyze",
                severity=Severity.INFO,
                score_impact=0,
            )]
        
        has_jsonld = "json-ld" in [f.lower() for f in formats] or any(
            isinstance(s, dict) and s.get("@context") and s.get("@type")
            for s in schema_markup
        )
        
        if has_jsonld:
            return [self._create_result(
                passed=True,
                message="JSON-LD schema format detected",
                severity=Severity.PASSED,
                score_impact=0,
                data={"formats": formats, "jsonld_count": len(schema_markup)},
            )]
        
        return [self._create_result(
            passed=False,
            message="Schema markup found but JSON-LD format not detected",
            severity=Severity.INFO,
            score_impact=-1,
            recommendation="Use JSON-LD format for structured data (Google recommended)",
            data={"formats": formats, "schema_count": len(schema_markup)},
        )]