"""
Technical SEO Rules.
"""
from typing import Any, Dict, List

from app.modules.scorer.services.base_rule import BaseRule
from app.modules.scorer.models.rule_result import RuleResult, Severity


class SSL_CertificateRule(BaseRule):
    """Check SSL certificate and HTTPS usage."""
    rule_id = "technical_001"
    name = "SSL Certificate"
    category = "technical"
    description = "Website must use HTTPS with valid SSL certificate"
    weight = 1.5
    tags = ["critical", "technical", "security"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        http = data.get("http", {})
        url_info = data.get("url", {})
        ssl = data.get("ssl", {})
        
        # Check URL scheme
        is_https = url_info.get("https", False)
        
        # Check SSL certificate details if available
        ssl_valid = ssl.get("valid", False) if ssl else False
        ssl_issuer = ssl.get("issuer", "") if ssl else ""
        
        if is_https and ssl_valid:
            return [self._create_result(
                passed=True,
                message=f"Valid SSL certificate present (HTTPS) - Issuer: {ssl_issuer or 'Valid'}",
                severity=Severity.PASSED,
                score_impact=0,
                data={"ssl_valid": True, "issuer": ssl_issuer},
            )]
        
        if is_https and not ssl_valid:
            return [self._create_result(
                passed=False,
                message="HTTPS detected but SSL certificate has issues",
                severity=Severity.CRITICAL,
                score_impact=-15,
                recommendation="Fix SSL certificate issues. Ensure certificate is valid and trusted",
                data={"ssl_valid": False},
            )]
        
        return [self._create_result(
            passed=False,
            message="Website is not using HTTPS",
            severity=Severity.CRITICAL,
            score_impact=-15,
            recommendation="Install SSL certificate and redirect all traffic to HTTPS",
            data={"ssl_valid": False, "using_https": False},
        )]


class MobileViewportRule(BaseRule):
    """Check mobile viewport meta tag."""
    rule_id = "technical_002"
    name = "Mobile Viewport"
    category = "technical"
    description = "Page should have viewport meta tag for mobile devices"
    weight = 1.3
    tags = ["critical", "technical", "mobile"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        basic = data.get("basic", {})
        viewport = basic.get("viewport", "")
        
        if not viewport:
            return [self._create_result(
                passed=False,
                message="Missing viewport meta tag",
                severity=Severity.CRITICAL,
                score_impact=-10,
                recommendation="Add <meta name='viewport' content='width=device-width, initial-scale=1.0'>",
            )]
        
        # Check if viewport is properly configured
        viewport_lower = viewport.lower()
        has_width = "width=device-width" in viewport_lower
        has_initial_scale = "initial-scale=1" in viewport_lower
        
        if has_width and has_initial_scale:
            return [self._create_result(
                passed=True,
                message="Viewport meta tag is properly configured",
                severity=Severity.PASSED,
                score_impact=0,
                data={"viewport": viewport},
            )]
        
        return [self._create_result(
            passed=False,
            message=f"Viewport meta tag present but may not be optimal: {viewport}",
            severity=Severity.WARNING,
            score_impact=-3,
            recommendation="Ensure viewport includes 'width=device-width, initial-scale=1.0'",
            data={"viewport": viewport, "has_width": has_width, "has_initial_scale": has_initial_scale},
        )]


class LanguageDeclarationRule(BaseRule):
    """Check HTML language attribute."""
    rule_id = "technical_003"
    name = "Language Declaration"
    category = "technical"
    description = "HTML should declare language for accessibility and SEO"
    weight = 1.0
    tags = ["warning", "technical", "accessibility"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        basic = data.get("basic", {})
        language = basic.get("language", "")
        
        if not language:
            return [self._create_result(
                passed=False,
                message="HTML language attribute not specified",
                severity=Severity.WARNING,
                score_impact=-5,
                recommendation="Add lang attribute to <html> tag (e.g., <html lang='en'>)",
            )]
        
        return [self._create_result(
            passed=True,
            message=f"Language declared: {language}",
            severity=Severity.PASSED,
            score_impact=0,
            data={"language": language},
        )]


class CharsetRule(BaseRule):
    """Check character encoding declaration."""
    rule_id = "technical_004"
    name = "Character Encoding"
    category = "technical"
    description = "Page should declare character encoding (UTF-8)"
    weight = 1.0
    tags = ["warning", "technical"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        basic = data.get("basic", {})
        charset = basic.get("charset", "")
        
        if not charset:
            return [self._create_result(
                passed=False,
                message="Character encoding not specified",
                severity=Severity.WARNING,
                score_impact=-5,
                recommendation="Add <meta charset='UTF-8'> in the first 1024 bytes of HTML",
            )]
        
        charset_lower = charset.lower()
        if "utf-8" in charset_lower or "utf8" in charset_lower:
            return [self._create_result(
                passed=True,
                message=f"Character encoding declared: {charset}",
                severity=Severity.PASSED,
                score_impact=0,
                data={"charset": charset},
            )]
        
        return [self._create_result(
            passed=False,
            message=f"Character encoding is {charset} (UTF-8 recommended)",
            severity=Severity.INFO,
            score_impact=-2,
            recommendation="Use UTF-8 encoding for better compatibility",
            data={"charset": charset},
        )]


class DoctypeRule(BaseRule):
    """Check DOCTYPE declaration."""
    rule_id = "technical_005"
    name = "DOCTYPE Declaration"
    category = "technical"
    description = "HTML5 DOCTYPE should be declared"
    weight = 1.0
    tags = ["critical", "technical"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        basic = data.get("basic", {})
        doctype = basic.get("doctype", "")
        
        if not doctype:
            return [self._create_result(
                passed=False,
                message="Missing DOCTYPE declaration",
                severity=Severity.CRITICAL,
                score_impact=-10,
                recommendation="Add <!DOCTYPE html> at the very beginning of the document",
            )]
        
        if "<!DOCTYPE html>" in doctype.lower():
            return [self._create_result(
                passed=True,
                message="HTML5 DOCTYPE declared",
                severity=Severity.PASSED,
                score_impact=0,
                data={"doctype": doctype},
            )]
        
        return [self._create_result(
            passed=False,
            message=f"Non-standard DOCTYPE: {doctype}",
            severity=Severity.WARNING,
            score_impact=-5,
            recommendation="Use HTML5 DOCTYPE: <!DOCTYPE html>",
            data={"doctype": doctype},
        )]


class HtmlLangRule(BaseRule):
    """Check HTML lang attribute matches content."""
    rule_id = "technical_006"
    name = "HTML Language Attribute"
    category = "technical"
    description = "HTML lang attribute should be set correctly"
    weight = 0.9
    tags = ["warning", "technical", "accessibility"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        basic = data.get("basic", {})
        language = basic.get("language", "")
        
        if not language:
            return [self._create_result(
                passed=False,
                message="HTML lang attribute not set",
                severity=Severity.WARNING,
                score_impact=-5,
                recommendation="Add lang attribute to <html> tag (e.g., <html lang='en'>)",
            )]
        
        # Validate language format (should be like 'en', 'en-US', etc.)
        if len(language) >= 2 and language[:2].isalpha():
            return [self._create_result(
                passed=True,
                message=f"HTML language properly declared: {language}",
                severity=Severity.PASSED,
                score_impact=0,
                data={"language": language},
            )]
        
        return [self._create_result(
            passed=False,
            message=f"Invalid language format: {language}",
            severity=Severity.WARNING,
            score_impact=-3,
            recommendation="Use standard language codes (e.g., 'en', 'en-US', 'es')",
            data={"language": language},
        )]


class SecurityHeadersRule(BaseRule):
    """Check security headers."""
    rule_id = "technical_007"
    name = "Security Headers"
    category = "technical"
    description = "Check for important security HTTP headers"
    weight = 1.2
    tags = ["critical", "technical", "security"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        http = data.get("http", {})
        headers = http.get("headers", {})
        security_headers = data.get("security_headers", {})
        
        important_headers = {
            "x-frame-options": "Prevents clickjacking",
            "x-content-type-options": "Prevents MIME sniffing",
            "strict-transport-security": "Enforces HTTPS",
            "content-security-policy": "Prevents XSS attacks",
            "x-xss-protection": "Enables XSS filter",
        }
        
        present = []
        missing = []
        
        for header, description in important_headers.items():
            # Check both raw headers and security_headers section
            header_value = headers.get(header) or security_headers.get(header, "")
            if header_value:
                present.append(header)
            else:
                missing.append(header)
        
        if not missing:
            return [self._create_result(
                passed=True,
                message=f"All critical security headers present ({len(present)}/{len(important_headers)})",
                severity=Severity.PASSED,
                score_impact=0,
                data={"present": present},
            )]
        
        impact = -len(missing) * 3
        severity = Severity.CRITICAL if len(missing) >= 3 else Severity.WARNING
        
        return [self._create_result(
            passed=False,
            message=f"Missing security headers: {', '.join(missing)} ({len(present)}/{len(important_headers)} present)",
            severity=severity,
            score_impact=impact,
            recommendation=f"Add missing security headers: {', '.join(missing)}",
            data={"present": present, "missing": missing},
        )]


class RobotsTxtRule(BaseRule):
    """Check robots.txt file."""
    rule_id = "technical_008"
    name = "Robots.txt"
    category = "technical"
    description = "Check robots.txt file for directives"
    weight = 0.8
    tags = ["info", "technical", "crawling"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        robots = data.get("robots", {})
        
        if not robots:
            return [self._create_result(
                passed=True,
                message="No robots.txt data available",
                severity=Severity.INFO,
                score_impact=0,
                recommendation="Ensure robots.txt exists and is properly configured",
            )]
        
        has_rules = robots.get("has_rules", False)
        sitemap_mentioned = robots.get("sitemap_mentioned", False)
        
        if not has_rules:
            return [self._create_result(
                passed=True,
                message="Robots.txt exists but has no rules (allows all)",
                severity=Severity.INFO,
                score_impact=0,
            )]
        
        issues = []
        if not sitemap_mentioned:
            issues.append("Sitemap not mentioned")
        
        if issues:
            return [self._create_result(
                passed=False,
                message=f"Robots.txt issues: {', '.join(issues)}",
                severity=Severity.INFO,
                score_impact=-2,
                recommendation="Add sitemap reference to robots.txt",
                data={"robots": robots},
            )]
        
        return [self._create_result(
            passed=True,
            message="Robots.txt is properly configured",
            severity=Severity.PASSED,
            score_impact=0,
            data={"robots": robots},
        )]


class SitemapRule(BaseRule):
    """Check for sitemap."""
    rule_id = "technical_009"
    name = "XML Sitemap"
    category = "technical"
    description = "Website should have XML sitemap"
    weight = 0.9
    tags = ["info", "technical", "indexing"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        sitemap = data.get("sitemap", {})
        
        if not sitemap:
            return [self._create_result(
                passed=False,
                message="No sitemap data available",
                severity=Severity.INFO,
                score_impact=-2,
                recommendation="Create and submit XML sitemap to search engines",
            )]
        
        sitemap_urls = sitemap.get("urls", [])
        url_count = len(sitemap_urls) if sitemap_urls else 0
        
        if url_count > 0:
            return [self._create_result(
                passed=True,
                message=f"XML sitemap found with {url_count} URLs",
                severity=Severity.PASSED,
                score_impact=0,
                data={"url_count": url_count},
            )]
        
        return [self._create_result(
            passed=False,
            message="Sitemap found but appears empty",
            severity=Severity.WARNING,
            score_impact=-3,
            recommendation="Ensure sitemap contains all important pages",
            data={"sitemap": sitemap},
        )]


class StructuredDataRule(BaseRule):
    """Check structured data / schema markup."""
    rule_id = "technical_010"
    name = "Structured Data"
    category = "technical"
    description = "Page should have structured data markup"
    weight = 1.0
    tags = ["warning", "technical", "rich_snippets"]
    
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