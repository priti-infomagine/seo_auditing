"""
Technical SEO Rules.
"""
from typing import Any, Dict, List

from app.modules.scorer.services.base_rule import BaseRule
from app.modules.rule_engine.models.rule_result import RuleResult, Severity
from urllib.parse import urlparse, parse_qsl
import re

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
        ssl = data.get("ssl", {}) or {}
        status_code = http.get("status_code", 0)
        
        is_https = url_info.get("https", False)
        ssl_valid = ssl.get("valid")
        ssl_issuer = ssl.get("issuer", "")
        ssl_expiry = ssl.get("expiry_date", "")
        ssl_error = ssl.get("error", "")
        
        if not is_https:
            return [self._create_result(
                passed=False,
                message="Website is not using HTTPS",
                severity=Severity.CRITICAL,
                score_impact=-15,
                recommendation="Install SSL certificate and redirect all traffic to HTTPS",
                data={"using_https": False, "ssl_valid": False},
            )]
        
        if ssl_valid is True:
            return [self._create_result(
                passed=True,
                message=f"Valid SSL certificate present (HTTPS) - Issuer: {ssl_issuer or 'Valid'}",
                severity=Severity.PASSED,
                score_impact=0,
                data={"ssl_valid": True, "issuer": ssl_issuer, "expiry_date": ssl_expiry},
            )]
        
        if ssl_valid is False:
            return [self._create_result(
                passed=False,
                message=f"HTTPS detected but SSL certificate has issues: {ssl_error or 'invalid'}",
                severity=Severity.WARNING,
                score_impact=-5,
                recommendation="Fix SSL certificate issues. Ensure certificate is valid and trusted",
                data={"ssl_valid": False, "issuer": ssl_issuer, "error": ssl_error},
            )]
        
        return [self._create_result(
            passed=True,
            message="HTTPS confirmed (deep SSL validation not available from crawler)",
            severity=Severity.INFO,
            score_impact=0,
            data={"ssl_valid": None, "using_https": True, "issuer": ssl_issuer},
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
                severity=Severity.WARNING,
                score_impact=-2,
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

        lower_doctype = doctype.lower()
        if "<!doctype" in lower_doctype:
            message = f"Legacy DOCTYPE: {doctype}"
            recommendation = "Consider using HTML5 DOCTYPE: <!DOCTYPE html>"
        else:
            message = f"Malformed DOCTYPE: {doctype}"
            recommendation = "Fix DOCTYPE declaration or use HTML5 DOCTYPE: <!DOCTYPE html>"

        return [self._create_result(
            passed=False,
            message=message,
            severity=Severity.WARNING,
            score_impact=-1,
            recommendation=recommendation,
            data={"doctype": doctype},
        )]



# class DoctypeRule(BaseRule):
#     """Check DOCTYPE declaration."""
#     rule_id = "technical_005"
#     name = "DOCTYPE Declaration"
#     category = "technical"
#     description = "HTML5 DOCTYPE should be declared"
#     weight = 1.0
#     tags = ["critical", "technical"]
    
#     async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
#         basic = data.get("basic", {})
#         doctype = basic.get("doctype", "")
        
#         if not doctype:
#             return [self._create_result(
#                 passed=False,
#                 message="Missing DOCTYPE declaration",
#                 severity=Severity.CRITICAL,
#                 score_impact=-10,
#                 recommendation="Add <!DOCTYPE html> at the very beginning of the document",
#             )]
        
#         if "<!DOCTYPE html>" in doctype.lower():
#             return [self._create_result(
#                 passed=True,
#                 message="HTML5 DOCTYPE declared",
#                 severity=Severity.PASSED,
#                 score_impact=0,
#                 data={"doctype": doctype},
#             )]
        
#         return [self._create_result(
#             passed=False,
#             message=f"Non-standard DOCTYPE: {doctype}",
#             severity=Severity.WARNING,
#             score_impact=-5,
#             recommendation="Use HTML5 DOCTYPE: <!DOCTYPE html>",
#             data={"doctype": doctype},
#         )]


# class SecurityHeadersRule(BaseRule):
#     """Check security headers."""
#     rule_id = "technical_007"
#     name = "Security Headers"
#     category = "technical"
#     description = "Check for important security HTTP headers"
#     weight = 1.2
#     tags = ["critical", "technical", "security"]
    
#     async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
#         http = data.get("http", {})
#         headers = http.get("headers", {})
#         security_headers = data.get("security_headers", {})
        
#         important_headers = {
#             "x-frame-options": "Prevents clickjacking",
#             "x-content-type-options": "Prevents MIME sniffing",
#             "strict-transport-security": "Enforces HTTPS",
#             "content-security-policy": "Prevents XSS attacks",
#             "x-xss-protection": "Enables XSS filter",
#         }
        
#         present = []
#         missing = []
        
#         for header, description in important_headers.items():
#             # Check both raw headers and security_headers section
#             header_value = headers.get(header) or security_headers.get(header, "")
#             if header_value:
#                 present.append(header)
#             else:
#                 missing.append(header)
        
#         if not missing:
#             return [self._create_result(
#                 passed=True,
#                 message=f"All critical security headers present ({len(present)}/{len(important_headers)})",
#                 severity=Severity.PASSED,
#                 score_impact=0,
#                 data={"present": present},
#             )]
        
#         impact = -len(missing) * 3
#         severity = Severity.CRITICAL if len(missing) >= 3 else Severity.WARNING
        
#         return [self._create_result(
#             passed=False,
#             message=f"Missing security headers: {', '.join(missing)} ({len(present)}/{len(important_headers)} present)",
#             severity=severity,
#             score_impact=impact,
#             recommendation=f"Add missing security headers: {', '.join(missing)}",
#             data={"present": present, "missing": missing},
#         )]

class SecurityHeadersRule(BaseRule):
    """Check security headers."""
    rule_id = "technical_007"
    name = "Security Headers"
    category = "technical"
    description = "Check for important security HTTP headers"
    weight = 1.2
    tags = ["warning", "technical", "security"]

    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        http = data.get("http", {})
        headers = http.get("headers", {})
        security_headers = data.get("security_headers", {})

        # Recommended severities:
        #   strict-transport-security      -> medium / -2
        #   content-security-policy        -> medium / -2
        #   x-frame-options                -> low    / -1
        #   x-content-type-options         -> low    / -1
        #   x-xss-protection               -> obsolete / 0
        required_headers = {
            "strict-transport-security": -2,
            "content-security-policy": -2,
        }
        optional_headers = {
            "x-frame-options": -1,
            "x-content-type-options": -1,
        }
        obsolete_headers = {
            "x-xss-protection": 0,
        }

        present = []
        missing_required = []
        missing_optional = []
        obsolete_missing = []

        for header, impact in required_headers.items():
            header_value = headers.get(header) or security_headers.get(header, "")
            if header_value:
                present.append(header)
            else:
                missing_required.append(header)

        for header, impact in optional_headers.items():
            header_value = headers.get(header) or security_headers.get(header, "")
            if header_value:
                present.append(header)
            else:
                missing_optional.append(header)

        for header, impact in obsolete_headers.items():
            header_value = headers.get(header) or security_headers.get(header, "")
            if header_value:
                present.append(header)
            else:
                obsolete_missing.append(header)

        if not missing_required and not missing_optional:
            return [self._create_result(
                passed=True,
                message=f"Security headers present ({len(present)}/{len(required_headers) + len(optional_headers) + len(obsolete_headers)})",
                severity=Severity.PASSED,
                score_impact=0,
                data={"present": present, "missing_required": [], "missing_optional": [], "obsolete_missing": obsolete_missing},
            )]

        impact = sum(required_headers[h] for h in missing_required) + sum(optional_headers[h] for h in missing_optional)
        missing_all = missing_required + missing_optional

        if missing_required:
            severity = Severity.WARNING
            message = (
                f"Missing security headers: {', '.join(missing_all)} "
                f"({len(present)}/{len(required_headers) + len(optional_headers) + len(obsolete_headers)} present)"
            )
            recommendation = (
                f"Add missing security headers: {', '.join(missing_required)}; "
                f"consider adding: {', '.join(missing_optional)}"
            )
        elif len(missing_optional) >= 2:
            severity = Severity.WARNING
            message = (
                f"Missing optional security headers: {', '.join(missing_optional)} "
                f"({len(present)}/{len(required_headers) + len(optional_headers) + len(obsolete_headers)} present)"
            )
            recommendation = f"Consider adding missing security headers: {', '.join(missing_optional)}"
        else:
            severity = Severity.INFO
            message = (
                f"Missing optional security headers: {', '.join(missing_optional)} "
                f"({len(present)}/{len(required_headers) + len(optional_headers) + len(obsolete_headers)} present)"
            )
            recommendation = f"Consider adding missing security headers: {', '.join(missing_optional)}"

        return [self._create_result(
            passed=False,
            message=message,
            severity=severity,
            score_impact=impact,
            recommendation=recommendation,
            data={"present": present, "missing_required": missing_required, "missing_optional": missing_optional, "obsolete_missing": obsolete_missing},
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
        
        # Check for blocking important resources
        disallowed = robots.get("disallowed_paths", [])
        important_paths = ["/css/", "/js/", "/images/", "/assets/"]
        blocked_important = [p for p in important_paths if any(p in d for d in disallowed)]
        if blocked_important:
            issues.append(f"Important resources blocked: {', '.join(blocked_important)}")
        
        if issues:
            return [self._create_result(
                passed=False,
                message=f"Robots.txt issues: {', '.join(issues)}",
                severity=Severity.INFO,
                score_impact=-2,
                recommendation="Add sitemap reference and ensure important resources are not blocked",
                data={"robots": robots, "issues": issues},
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
        valid_urls = sitemap.get("valid_urls", 0)
        error_urls = sitemap.get("error_urls", 0)
        
        details = {"url_count": url_count, "valid_urls": valid_urls, "error_urls": error_urls}
        
        if url_count > 0:
            msg = f"XML sitemap found with {url_count} URLs"
            if valid_urls:
                msg += f" ({valid_urls} valid)"
            if error_urls:
                msg += f" ({error_urls} with errors)"
            return [self._create_result(
                passed=True,
                message=msg,
                severity=Severity.PASSED,
                score_impact=0,
                data=details,
            )]
        
        return [self._create_result(
            passed=False,
            message="Sitemap found but appears empty",
            severity=Severity.WARNING,
            score_impact=-3,
            recommendation="Ensure sitemap contains all important pages",
            data=details,
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
                severity=Severity.INFO,
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


class UrlRule(BaseRule):
    """Check URL structure."""
    rule_id = "url_001"
    name = "URL Structure"
    category = "technical"
    description = "URLs should be clean and descriptive"
    weight = 0.8
    tags = ["info", "technical", "url"]

    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        url_info = data.get("url", {})
        url_path = url_info.get("path", "")
        normalized_url = url_info.get("normalized_url", "")

        if not url_path and not normalized_url:
            return [self._create_result(
                passed=True,
                message="No URL data available",
                severity=Severity.INFO,
                score_impact=0,
            )]

        issues = []
        details = {"path": url_path}

        if not url_path:
            issues.append("missing path")

        if "_" in url_path:
            issues.append("underscores in URL")

        if "%20" in url_path or " " in url_path:
            issues.append("spaces in URL")

        if len(url_path) > 100:
            issues.append("URL too long")

        if not issues:
            return [self._create_result(
                passed=True,
                message="URL structure is clean",
                severity=Severity.PASSED,
                score_impact=0,
                data=details,
            )]

        impact = -len(issues)
        return [self._create_result(
            passed=False,
            message=f"URL structure issues: {', '.join(issues)}",
            severity=Severity.INFO,
            score_impact=impact,
            recommendation="Use clean URLs with hyphens, lowercase, and no unnecessary parameters",
            data={**details, "issues": issues},
        )]


class MobileRule(BaseRule):
    """Check mobile friendliness."""
    rule_id = "mobile_001"
    name = "Mobile Friendliness"
    category = "technical"
    description = "Page should be mobile-friendly"
    weight = 1.0
    tags = ["warning", "technical", "mobile"]

    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        basic = data.get("basic", {})
        viewport = basic.get("viewport", "")

        if not viewport:
            return [self._create_result(
                passed=False,
                message="Missing viewport meta tag",
                severity=Severity.WARNING,
                score_impact=-5,
                recommendation="Add <meta name='viewport' content='width=device-width, initial-scale=1.0'>",
            )]

        viewport_lower = viewport.lower()
        has_width = "width=device-width" in viewport_lower
        has_initial_scale = "initial-scale=1" in viewport_lower

        if has_width and has_initial_scale:
            return [self._create_result(
                passed=True,
                message="Viewport properly configured for mobile",
                severity=Severity.PASSED,
                score_impact=0,
                data={"viewport": viewport},
            )]

        return [self._create_result(
            passed=False,
            message=f"Viewport may not be optimal: {viewport}",
            severity=Severity.INFO,
            score_impact=-2,
            recommendation="Ensure viewport includes 'width=device-width, initial-scale=1.0'",
            data={"viewport": viewport, "has_width": has_width, "has_initial_scale": has_initial_scale},
        )]


class HttpStatusRule(BaseRule):
    """Check HTTP status code handling."""
    rule_id = "http_status_001"
    name = "HTTP Status Codes"
    category = "technical"
    description = "Check HTTP status codes and redirect handling"
    weight = 1.2
    tags = ["critical", "technical", "http"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        http = data.get("http", {})
        status_code = http.get("status_code", 0)
        redirects = http.get("redirects", [])
        
        if status_code == 200:
            return [self._create_result(
                passed=True,
                message="Page returns 200 OK",
                severity=Severity.PASSED,
                score_impact=0,
                data={"status_code": status_code},
            )]
        
        if status_code in (301, 308):
            return [self._create_result(
                passed=True,
                message=f"Permanent redirect ({status_code})",
                severity=Severity.PASSED,
                score_impact=0,
                data={"status_code": status_code},
            )]
        
        if status_code in (302, 307):
            return [self._create_result(
                passed=False,
                message=f"Temporary redirect ({status_code}) - consider permanent redirect",
                severity=Severity.WARNING,
                score_impact=-2,
                recommendation="Use 301/308 permanent redirects for SEO",
                data={"status_code": status_code},
            )]
        
        if status_code == 404:
            return [self._create_result(
                passed=False,
                message="Page not found (404)",
                severity=Severity.WARNING,
                score_impact=-3,
                recommendation="Fix broken link or set up custom 404 page",
                data={"status_code": status_code},
            )]
        
        if status_code == 410:
            return [self._create_result(
                passed=False,
                message="Page permanently removed (410)",
                severity=Severity.WARNING,
                score_impact=-3,
                recommendation="Ensure 410 is intentional and links are updated",
                data={"status_code": status_code},
            )]
        
        if status_code in (429, 500, 502, 503, 504):
            return [self._create_result(
                passed=False,
                message=f"Server error ({status_code})",
                severity=Severity.CRITICAL,
                score_impact=-10,
                recommendation="Fix server error and ensure page is accessible",
                data={"status_code": status_code},
            )]
        
        return [self._create_result(
            passed=False,
            message=f"Unexpected status code: {status_code}",
            severity=Severity.WARNING,
            score_impact=-3,
            recommendation="Investigate and resolve HTTP status code",
            data={"status_code": status_code},
        )]


class HreflangRule(BaseRule):
    """Check hreflang annotations."""
    rule_id = "hreflang_001"
    name = "Hreflang"
    category = "technical"
    description = "Check hreflang for international targeting"
    weight = 0.8
    tags = ["info", "technical", "international"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        hreflang = data.get("hreflang", [])
        
        if not hreflang:
            return [self._create_result(
                passed=True,
                message="No hreflang annotations (not applicable or not used)",
                severity=Severity.INFO,
                score_impact=0,
            )]
        
        issues = []
        details = {"hreflang_count": len(hreflang)}
        
        # Check for self-reference
        url_info = data.get("url", {})
        current_url = url_info.get("url", "") or url_info.get("normalized_url", "")
        has_self = any(h.get("href", "") == current_url for h in hreflang if isinstance(h, dict))
        if not has_self:
            issues.append("missing self-referencing hreflang")
            details["has_self_reference"] = False
        
        # Check for x-default
        has_xdefault = any(h.get("hreflang", "").lower() == "x-default" for h in hreflang if isinstance(h, dict))
        if not has_xdefault:
            issues.append("missing x-default")
            details["has_x_default"] = False
        
        if issues:
            return [self._create_result(
                passed=False,
                message=f"Hreflang issues: {', '.join(issues)}",
                severity=Severity.INFO,
                score_impact=-1,
                recommendation="Ensure hreflang includes self-reference and x-default",
                data=details,
            )]
        
        return [self._create_result(
            passed=True,
            message=f"Hreflang properly configured ({len(hreflang)} entries)",
            severity=Severity.PASSED,
            score_impact=0,
            data=details,
        )]