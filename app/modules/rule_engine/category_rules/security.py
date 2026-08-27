"""
Security SEO Rules.
"""
from typing import Any, Dict, List

from app.modules.scorer.services.base_rule import BaseRule
from app.modules.rule_engine.models.rule_result import RuleResult, Severity


class HTTPSRule(BaseRule):
    """Check HTTPS usage."""
    rule_id = "security_001"
    name = "HTTPS"
    category = "security"
    description = "Website must use HTTPS"
    weight = 1.5
    tags = ["critical", "security", "https"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        url_info = data.get("url", {})
        is_https = url_info.get("https", False)
        
        if is_https:
            return [self._create_result(
                passed=True,
                message="Website uses HTTPS",
                severity=Severity.PASSED,
                score_impact=0,
            )]
        
        return [self._create_result(
            passed=False,
            message="Website does not use HTTPS",
            severity=Severity.CRITICAL,
            score_impact=-15,
            recommendation="Install SSL certificate and enable HTTPS",
        )]


class MixedContentRule(BaseRule):
    """Check for mixed content (HTTP resources on HTTPS page)."""
    rule_id = "security_002"
    name = "Mixed Content"
    category = "security"
    description = "No mixed content on HTTPS pages"
    weight = 1.3
    tags = ["critical", "security", "https"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        security = data.get("security", {})
        mixed_content = security.get("mixed_content", [])
        
        if not mixed_content:
            return [self._create_result(
                passed=True,
                message="No mixed content detected",
                severity=Severity.PASSED,
                score_impact=0,
            )]
        
        return [self._create_result(
            passed=False,
            message=f"Found {len(mixed_content)} mixed content resources (HTTP on HTTPS)",
            severity=Severity.CRITICAL,
            score_impact=-10,
            recommendation="Update all resources to use HTTPS",
            data={"mixed_content_count": len(mixed_content), "samples": mixed_content[:5]},
        )]


class SecurityHeadersRule(BaseRule):
    """Check security headers."""
    rule_id = "security_003"
    name = "Security Headers"
    category = "security"
    description = "Check for important security HTTP headers"
    weight = 1.2
    tags = ["critical", "security", "headers"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        http = data.get("http", {})
        headers = http.get("headers", {})
        security_headers = data.get("security_headers", {})
        
        important_headers = {
            "content-security-policy": "Helps mitigate XSS and injection attacks",
            "strict-transport-security": "Enforces HTTPS",
            "x-content-type-options": "Prevents MIME sniffing",
            "x-frame-options": "Helps prevent clickjacking",
            "referrer-policy": "Controls referrer information",
            "permissions-policy": "Controls access to browser features",
        }
        
        present = []
        missing = []
        
        for header, description in important_headers.items():
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


class SSLCertificateRule(BaseRule):
    """Check SSL certificate validity."""
    rule_id = "security_004"
    name = "SSL Certificate"
    category = "security"
    description = "SSL certificate must be valid and trusted"
    weight = 1.4
    tags = ["critical", "security", "ssl"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        ssl = data.get("ssl", {})
        
        if not ssl:
            return [self._create_result(
                passed=False,
                message="No SSL certificate information available",
                severity=Severity.WARNING,
                score_impact=-5,
                recommendation="Ensure SSL certificate is properly configured",
            )]
        
        is_valid = ssl.get("valid", False)
        issuer = ssl.get("issuer", "")
        expiry_date = ssl.get("expiry_date", "")
        
        if not is_valid:
            return [self._create_result(
                passed=False,
                message="SSL certificate is not valid",
                severity=Severity.CRITICAL,
                score_impact=-15,
                recommendation="Fix SSL certificate issues",
                data={"ssl": ssl},
            )]
        
        return [self._create_result(
            passed=True,
            message=f"Valid SSL certificate from {issuer or 'trusted CA'}",
            severity=Severity.PASSED,
            score_impact=0,
            data={"issuer": issuer, "expiry_date": expiry_date},
        )]


class HSTSRule(BaseRule):
    """Check HTTP Strict Transport Security."""
    rule_id = "security_005"
    name = "HSTS"
    category = "security"
    description = "HSTS header enforces HTTPS connections"
    weight = 1.0
    tags = ["warning", "security", "headers"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        http = data.get("http", {})
        headers = http.get("headers", {})
        hsts = headers.get("strict-transport-security", "")
        
        if not hsts:
            return [self._create_result(
                passed=False,
                message="HSTS header not found",
                severity=Severity.WARNING,
                score_impact=-5,
                recommendation="Add Strict-Transport-Security header",
            )]
        
        # Check max-age
        if "max-age=" in hsts:
            try:
                max_age = int(hsts.split("max-age=")[1].split(";")[0].strip())
                if max_age >= 31536000:  # 1 year
                    return [self._create_result(
                        passed=True,
                        message="HSTS properly configured with long max-age",
                        severity=Severity.PASSED,
                        score_impact=0,
                        data={"hsts": hsts},
                    )]
            except (ValueError, IndexError):
                pass
        
        return [self._create_result(
            passed=False,
            message=f"HSTS present but may need adjustment: {hsts}",
            severity=Severity.INFO,
            score_impact=-2,
            recommendation="Set HSTS max-age to at least 1 year (31536000)",
            data={"hsts": hsts},
        )]

class XSSProtectionRule(BaseRule):
    """Check XSS protection."""
    rule_id = "security_006"
    name = "XSS Protection"
    category = "security"
    description = "Check XSS protection headers"
    weight = 1.0
    tags = ["warning", "security", "xss"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        http = data.get("http", {})
        headers = http.get("headers", {})
        
        xss_protection = headers.get("x-xss-protection", "")
        csp = headers.get("content-security-policy", "")
        
        if xss_protection or csp:
            return [self._create_result(
                passed=True,
                message="XSS protection headers present",
                severity=Severity.PASSED,
                score_impact=0,
                data={"x_xss_protection": xss_protection, "csp": csp},
            )]
        
        return [self._create_result(
            passed=False,
            message="No XSS protection headers found",
            severity=Severity.WARNING,
            score_impact=-5,
            recommendation="Add X-XSS-Protection and Content-Security-Policy headers",
        )]