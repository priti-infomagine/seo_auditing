"""
Security SEO Rules - 14 comprehensive security checks.

Rule IDs:
- security_001: HTTPS Redirect (HTTP→HTTPS with 301/308)
- security_002: Mixed Content (HTTP resources on HTTPS page)
- security_003: Security Headers (general check - legacy)
- security_004: SSL Certificate (legacy - use security_007 for TLS config)
- security_005: HSTS Header
- security_006: XSS Protection (legacy)
- security_007: TLS Configuration
- security_008: Content Security Policy
- security_009: X-Frame-Options
- security_010: X-Content-Type-Options
- security_011: Permissions Policy
- security_012: Referrer Policy
- security_013: External Links Security
- security_014: Form HTTPS Actions
- security_015: No Leaked Secrets
- security_016: No Password Fields on HTTP
- security_017: No Protocol-Relative URLs
"""
from __future__ import annotations
import re
from typing import Any, Dict, List
from urllib.parse import urljoin

from app.modules.scorer.services.base_rule import BaseRule
from app.modules.rule_engine.models.rule_result import RuleResult, Severity


# ────────────────────────────────────────────────────────────────────────────
# Helper functions
# ────────────────────────────────────────────────────────────────────────────

WEAK_CIPHERS = {
    "RC4", "DES", "3DES", "IDEA", "SEED", "RC2", "NULL",
    "EXPORT", "ANON", "AECDH", "ECDH_ANON"
}

WEAK_TLS_VERSIONS = {"SSLv2", "SSLv3", "TLSv1", "TLSv1.1"}


def _is_weak_cipher(cipher: str) -> bool:
    if not cipher:
        return False
    cipher_upper = cipher.upper()
    return any(weak in cipher_upper for weak in WEAK_CIPHERS)


def _extract_protocol_relative_urls(html: str, base_url: str) -> List[str]:
    """Find all //... URLs in src, href, action attributes."""
    pattern = re.compile(
        r'(?:src|href|action|data-src|data-href)\s*=\s*["\']//([^"\'>\s]+)',
        re.IGNORECASE
    )
    matches = pattern.findall(html)
    return [f"//{m}" for m in matches]


def _extract_form_actions(html: str, base_url: str) -> List[Dict[str, str]]:
    """Extract all <form action="..."> and resolve to absolute URLs."""
    forms = []
    form_pattern = re.compile(r'<form\b[^>]*action\s*=\s*["\']([^"\']*)["\']', re.IGNORECASE)
    for match in form_pattern.finditer(html):
        action = match.group(1)
        resolved = urljoin(base_url, action) if action else base_url
        forms.append({"action": action, "resolved": resolved})
    return forms


def _extract_mixed_content(html: str, page_url: str) -> Dict[str, List[str]]:
    """Find HTTP resources on HTTPS page."""
    if not page_url.startswith("https://"):
        return {"active": [], "passive": []}
    
    active_patterns = [
        r'<script\b[^>]*src\s*=\s*["\']([^"\']+)["\']',
        r'<link\b[^>]*rel\s*=\s*["\']stylesheet[^"\']*href\s*=\s*["\']([^"\']+)["\']',
        r'<iframe\b[^>]*src\s*=\s*["\']([^"\']+)["\']',
        r'<object\b[^>]*data\s*=\s*["\']([^"\']+)["\']',
    ]
    passive_patterns = [
        r'<img\b[^>]*src\s*=\s*["\']([^"\']+)["\']',
        r'<audio\b[^>]*src\s*=\s*["\']([^"\']+)["\']',
        r'<video\b[^>]*src\s*=\s*["\']([^"\']+)["\']',
        r'<source\b[^>]*src\s*=\s*["\']([^"\']+)["\']',
        r'<link\b[^>]*rel\s*=\s*["\'](?:icon|preload|prefetch)[^"\']*href\s*=\s*["\']([^"\']+)["\']',
    ]
    
    active, passive = [], []
    for pattern in active_patterns:
        for match in re.finditer(pattern, html, re.IGNORECASE):
            url = match.group(1)
            if url.startswith("http://"):
                resolved = urljoin(page_url, url)
                active.append(resolved)
    for pattern in passive_patterns:
        for match in re.finditer(pattern, html, re.IGNORECASE):
            url = match.group(1)
            if url.startswith("http://"):
                resolved = urljoin(page_url, url)
                passive.append(resolved)
    
    return {"active": active, "passive": passive}


def _has_password_field_on_http(html: str, final_url: str) -> bool:
    """Check if page has <input type="password"> and loads over HTTP."""
    if not final_url.startswith("http://"):
        return False
    return bool(re.search(r'<input\b[^>]*type\s*=\s*["\']password["\']', html, re.IGNORECASE))


def _scan_leaked_secrets(html: str, headers: Dict[str, str]) -> List[Dict[str, str]]:
    """Scan for API keys, tokens, passwords in HTML and headers."""
    findings = []
    
    secret_patterns = [
        (r'(?i)(?:api[_-]?key|apikey)\s*[:=]\s*["\']?([a-zA-Z0-9_\-]{20,})["\']?', "API Key"),
        (r'(?i)(?:secret[_-]?key|secretkey)\s*[:=]\s*["\']?([a-zA-Z0-9_\-]{20,})["\']?', "Secret Key"),
        (r'(?i)(?:access[_-]?token|accesstoken)\s*[:=]\s*["\']?([a-zA-Z0-9_\-]{20,})["\']?', "Access Token"),
        (r'(?i)(?:auth[_-]?token|authtoken)\s*[:=]\s*["\']?([a-zA-Z0-9_\-]{20,})["\']?', "Auth Token"),
        (r'(?i)password\s*[:=]\s*["\']([^"\']{8,})["\']', "Password"),
        (r'(?i)aws[_-]?(?:access[_-]?key|secret[_-]?key)\s*[:=]\s*["\']?([A-Z0-9]{20})["\']?', "AWS Credentials"),
        (r'(?i)sk_live_[a-zA-Z0-9]{24,}', "Stripe Secret Key"),
        (r'(?i)pk_live_[a-zA-Z0-9]{24,}', "Stripe Publishable Key"),
    ]
    
    for pattern, name in secret_patterns:
        for match in re.finditer(pattern, html):
            findings.append({
                "type": name,
                "context": match.group(0)[:100],
                "location": "html"
            })
    
    sensitive_headers = ["set-cookie", "authorization", "x-api-key", "x-auth-token"]
    for h in sensitive_headers:
        if h in headers:
            value = headers[h]
            if len(value) > 20:
                findings.append({
                    "type": f"Sensitive Header: {h}",
                    "context": value[:50] + "...",
                    "location": "header"
                })
    
    return findings


# ────────────────────────────────────────────────────────────────────────────
# 1. TLS Configuration (Check #1) - security_007
# ────────────────────────────────────────────────────────────────────────────
class TLSConfigurationRule(BaseRule):
    """Check TLS protocol version, certificate validity, and cipher strength."""
    rule_id = "security_007"
    name = "TLS Configuration"
    category = "security"
    description = "TLS must use 1.2+, valid cert, strong ciphers"
    weight = 1.5
    tags = ["critical", "security", "tls"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        site_sec = data.get("site_security", {})
        tls = site_sec.get("tls")
        
        if not tls:
            return [self._create_result(
                passed=False,
                message="TLS probe not available (no HTTPS endpoint?)",
                severity=Severity.WARNING,
                score_impact=-5,
                recommendation="Enable HTTPS and ensure TLS is properly configured",
            )]
        
        issues = []
        warnings = []
        
        # TLS Version
        version = tls.get("tls_version", "")
        if version in WEAK_TLS_VERSIONS:
            issues.append(f"Deprecated TLS version: {version}")
        elif version and version not in ("TLSv1.2", "TLSv1.3"):
            warnings.append(f"Unusual TLS version: {version}")
        
        # Legacy TLS acceptance
        if tls.get("tested_tls10") is True:
            issues.append("Server accepts TLS 1.0 (deprecated)")
        if tls.get("tested_tls11") is True:
            issues.append("Server accepts TLS 1.1 (deprecated)")
        
        # Certificate
        if not tls.get("certificate_valid"):
            issues.append("Certificate validation failed")
        else:
            expiry = tls.get("certificate_expiry")
            if expiry:
                from datetime import datetime, timedelta
                days_left = (expiry - datetime.utcnow()).days
                if days_left < 0:
                    issues.append(f"Certificate expired {abs(days_left)} days ago")
                elif days_left < 30:
                    warnings.append(f"Certificate expires in {days_left} days")
            
            # Check hostname match (SAN)
            hostname = site_sec.get("hostname", "")
            sans = tls.get("certificate_san", [])
            if hostname and not any(
                san == hostname or (san.startswith("*.") and hostname.endswith(san[1:]))
                for san in sans
            ):
                issues.append(f"Certificate SAN does not cover {hostname}")
        
        # Cipher
        cipher = tls.get("cipher", "")
        if _is_weak_cipher(cipher):
            issues.append(f"Weak cipher suite: {cipher}")
        
        # Chain trust
        if not tls.get("chain_trusted"):
            issues.append("Certificate chain not trusted")
        
        # Error from probe
        if tls.get("error"):
            issues.append(f"TLS probe error: {tls['error']}")
        
        if issues:
            return [self._create_result(
                passed=False,
                message="; ".join(issues),
                severity=Severity.CRITICAL,
                score_impact=-15,
                recommendation="Upgrade TLS to 1.2+, use strong ciphers, fix certificate issues",
                data={"issues": issues, "warnings": warnings, "tls": tls},
            )]
        
        if warnings:
            return [self._create_result(
                passed=True,
                message="TLS configured correctly; " + "; ".join(warnings),
                severity=Severity.WARNING,
                score_impact=-2,
                recommendation="Monitor certificate expiry; " + "; ".join(warnings),
                data={"warnings": warnings, "tls": tls},
            )]
        
        return [self._create_result(
            passed=True,
            message=f"TLS {version} with strong cipher ({cipher})",
            severity=Severity.PASSED,
            score_impact=0,
            data={"tls": tls},
        )]


# ────────────────────────────────────────────────────────────────────────────
# 2. HSTS Header (Check #2) - security_005
# ────────────────────────────────────────────────────────────────────────────
class HSTSHeaderRule(BaseRule):
    """Check Strict-Transport-Security header."""
    rule_id = "security_005"
    name = "HSTS Header"
    category = "security"
    description = "HSTS enforces HTTPS and prevents downgrade attacks"
    weight = 1.0
    tags = ["warning", "security", "headers"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        site_sec = data.get("site_security", {})
        hsts = site_sec.get("hsts_header", "")
        hsts_max_age = site_sec.get("hsts_max_age")
        include_sub = site_sec.get("hsts_include_subdomains", False)
        preload = site_sec.get("hsts_preload", False)
        
        if not hsts:
            return [self._create_result(
                passed=False,
                message="HSTS header missing",
                severity=Severity.WARNING,
                score_impact=-5,
                recommendation="Add Strict-Transport-Security header with max-age>=31536000",
            )]
        
        # Parse HSTS
        max_age = 0
        for part in hsts.split(";"):
            part = part.strip().lower()
            if part.startswith("max-age="):
                try:
                    max_age = int(part.split("=")[1])
                except (ValueError, IndexError):
                    pass
        
        issues = []
        if max_age < 31536000:  # 1 year
            issues.append(f"max-age={max_age} (recommended ≥31536000)")
        
        if not include_sub:
            issues.append("includeSubDomains missing")
        
        if not preload:
            issues.append("preload missing (recommended for HSTS preload list)")
        
        if issues:
            return [self._create_result(
                passed=False,
                message="HSTS present but suboptimal: " + "; ".join(issues),
                severity=Severity.WARNING,
                score_impact=-3,
                recommendation="Set max-age=31536000; includeSubDomains; preload",
                data={"hsts": hsts, "max_age": max_age, "issues": issues},
            )]
        
        return [self._create_result(
            passed=True,
            message=f"HSTS properly configured (max-age={max_age})",
            severity=Severity.PASSED,
            score_impact=0,
            data={"hsts": hsts, "include_subdomains": include_sub, "preload": preload},
        )]


# ────────────────────────────────────────────────────────────────────────────
# 3. Content Security Policy (Check #3) - security_008
# ────────────────────────────────────────────────────────────────────────────
class CSPRule(BaseRule):
    """Check Content-Security-Policy header."""
    rule_id = "security_008"
    name = "Content Security Policy"
    category = "security"
    description = "CSP mitigates XSS and injection attacks"
    weight = 1.2
    tags = ["warning", "security", "headers", "csp"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        site_sec = data.get("site_security", {})
        headers = site_sec.get("security_headers", {})
        csp = headers.get("content-security-policy", "")
        
        if not csp:
            return [self._create_result(
                passed=False,
                message="Content-Security-Policy header missing",
                severity=Severity.WARNING,
                score_impact=-5,
                recommendation="Implement CSP to restrict resource loading",
            )]
        
        issues = []
        csp_lower = csp.lower()
        
        if "unsafe-inline" in csp_lower:
            issues.append("Uses 'unsafe-inline' (weakens XSS protection)")
        if "unsafe-eval" in csp_lower:
            issues.append("Uses 'unsafe-eval' (allows eval())")
        
        critical_directives = ["script-src", "style-src", "object-src", "frame-src", "base-uri"]
        for directive in critical_directives:
            if f"{directive} *" in csp_lower or f"{directive}: *" in csp_lower:
                issues.append(f"{directive} allows '*' (too permissive)")
        
        if "frame-ancestors" not in csp_lower:
            issues.append("Missing frame-ancestors directive")
        
        if issues:
            return [self._create_result(
                passed=False,
                message="CSP present but has issues: " + "; ".join(issues),
                severity=Severity.WARNING,
                score_impact=-3,
                recommendation="Tighten CSP: remove unsafe-*, restrict wildcards, add frame-ancestors",
                data={"csp": csp, "issues": issues},
            )]
        
        return [self._create_result(
            passed=True,
            message="CSP properly configured",
            severity=Severity.PASSED,
            score_impact=0,
            data={"csp": csp},
        )]


# ────────────────────────────────────────────────────────────────────────────
# 4. X-Frame-Options (Check #4) - security_009
# ────────────────────────────────────────────────────────────────────────────
class XFrameOptionsRule(BaseRule):
    """Check X-Frame-Options header."""
    rule_id = "security_009"
    name = "X-Frame-Options"
    category = "security"
    description = "Prevents clickjacking via iframe embedding"
    weight = 1.0
    tags = ["warning", "security", "headers"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        site_sec = data.get("site_security", {})
        headers = site_sec.get("security_headers", {})
        xfo = headers.get("x-frame-options", "")
        
        if not xfo:
            # Check CSP frame-ancestors as alternative
            csp = headers.get("content-security-policy", "")
            if "frame-ancestors" in csp.lower():
                return [self._create_result(
                    passed=True,
                    message="Clickjacking protected via CSP frame-ancestors",
                    severity=Severity.PASSED,
                    score_impact=0,
                    data={"csp_frame_ancestors": True},
                )]
            
            return [self._create_result(
                passed=False,
                message="X-Frame-Options header missing",
                severity=Severity.WARNING,
                score_impact=-5,
                recommendation="Add X-Frame-Options: DENY or SAMEORIGIN, or CSP frame-ancestors",
            )]
        
        xfo_upper = xfo.upper()
        if xfo_upper not in ("DENY", "SAMEORIGIN"):
            return [self._create_result(
                passed=False,
                message=f"Invalid X-Frame-Options value: {xfo}",
                severity=Severity.WARNING,
                score_impact=-3,
                recommendation="Use DENY or SAMEORIGIN",
                data={"x_frame_options": xfo},
            )]
        
        return [self._create_result(
            passed=True,
            message=f"X-Frame-Options: {xfo}",
            severity=Severity.PASSED,
            score_impact=0,
            data={"x_frame_options": xfo},
        )]


# ────────────────────────────────────────────────────────────────────────────
# 5. X-Content-Type-Options (Check #5) - security_010
# ────────────────────────────────────────────────────────────────────────────
class XContentTypeOptionsRule(BaseRule):
    """Check X-Content-Type-Options header."""
    rule_id = "security_010"
    name = "X-Content-Type-Options"
    category = "security"
    description = "Prevents MIME type sniffing"
    weight = 1.0
    tags = ["warning", "security", "headers"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        site_sec = data.get("site_security", {})
        headers = site_sec.get("security_headers", {})
        xcto = headers.get("x-content-type-options", "")
        
        if not xcto or xcto.lower() != "nosniff":
            return [self._create_result(
                passed=False,
                message="X-Content-Type-Options: nosniff missing",
                severity=Severity.WARNING,
                score_impact=-3,
                recommendation="Add X-Content-Type-Options: nosniff header",
            )]
        
        return [self._create_result(
            passed=True,
            message="X-Content-Type-Options: nosniff present",
            severity=Severity.PASSED,
            score_impact=0,
        )]


# ────────────────────────────────────────────────────────────────────────────
# 6. Permissions Policy (Check #6) - security_011
# ────────────────────────────────────────────────────────────────────────────
class PermissionsPolicyRule(BaseRule):
    """Check Permissions-Policy header."""
    rule_id = "security_011"
    name = "Permissions Policy"
    category = "security"
    description = "Controls browser feature access (camera, microphone, etc.)"
    weight = 0.8
    tags = ["info", "security", "headers"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        site_sec = data.get("site_security", {})
        headers = site_sec.get("security_headers", {})
        pp = headers.get("permissions-policy", "")
        
        if not pp:
            return [self._create_result(
                passed=False,
                message="Permissions-Policy header missing",
                severity=Severity.INFO,
                score_impact=-1,
                recommendation="Add Permissions-Policy to restrict browser features",
            )]
        
        if "*" in pp and not pp.strip() == "*":
            return [self._create_result(
                passed=False,
                message="Permissions-Policy uses wildcard (*)",
                severity=Severity.INFO,
                score_impact=-1,
                recommendation="Restrict permissions to specific origins",
                data={"permissions_policy": pp},
            )]
        
        return [self._create_result(
            passed=True,
            message="Permissions-Policy present",
            severity=Severity.PASSED,
            score_impact=0,
            data={"permissions_policy": pp},
        )]


# ────────────────────────────────────────────────────────────────────────────
# 7. Referrer Policy (Check #7) - security_012
# ────────────────────────────────────────────────────────────────────────────
class ReferrerPolicyRule(BaseRule):
    """Check Referrer-Policy header."""
    rule_id = "security_012"
    name = "Referrer Policy"
    category = "security"
    description = "Controls referrer information sent with requests"
    weight = 0.8
    tags = ["info", "security", "headers"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        site_sec = data.get("site_security", {})
        headers = site_sec.get("security_headers", {})
        rp = headers.get("referrer-policy", "")
        
        valid_policies = {
            "no-referrer", "no-referrer-when-downgrade", "origin",
            "origin-when-cross-origin", "same-origin", "strict-origin",
            "strict-origin-when-cross-origin", "unsafe-url"
        }
        
        if not rp:
            return [self._create_result(
                passed=False,
                message="Referrer-Policy header missing",
                severity=Severity.INFO,
                score_impact=-1,
                recommendation="Add Referrer-Policy: strict-origin-when-cross-origin",
            )]
        
        rp_lower = rp.lower().strip()
        if rp_lower not in valid_policies:
            return [self._create_result(
                passed=False,
                message=f"Invalid Referrer-Policy value: {rp}",
                severity=Severity.WARNING,
                score_impact=-2,
                recommendation="Use a valid referrer policy",
                data={"referrer_policy": rp},
            )]
        
        if rp_lower == "unsafe-url":
            return [self._create_result(
                passed=False,
                message="Referrer-Policy: unsafe-url leaks full URL",
                severity=Severity.WARNING,
                score_impact=-2,
                recommendation="Use strict-origin-when-cross-origin or similar",
                data={"referrer_policy": rp},
            )]
        
        return [self._create_result(
            passed=True,
            message=f"Referrer-Policy: {rp}",
            severity=Severity.PASSED,
            score_impact=0,
            data={"referrer_policy": rp},
        )]


# ────────────────────────────────────────────────────────────────────────────
# 8. HTTPS Redirect (Check #8) - security_001
# ────────────────────────────────────────────────────────────────────────────
class HTTPSRedirectRule(BaseRule):
    """Check HTTP→HTTPS redirect."""
    rule_id = "security_001"
    name = "HTTPS Enforcement"
    category = "security"
    description = "Site must redirect HTTP to HTTPS with 301/308"
    weight = 1.5
    tags = ["critical", "security", "https"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        site_sec = data.get("site_security", {})
        http_redirect = site_sec.get("http_redirect")
        
        if not http_redirect:
            return [self._create_result(
                passed=False,
                message="HTTP redirect probe not available",
                severity=Severity.WARNING,
                score_impact=-5,
                recommendation="Ensure HTTP redirects to HTTPS",
            )]
        
        final_url = http_redirect.get("final_url", "")
        is_permanent = http_redirect.get("is_permanent_redirect", False)
        http_loads = http_redirect.get("http_loads_directly", False)
        cert_error = http_redirect.get("certificate_error", False)
        
        if http_loads:
            return [self._create_result(
                passed=False,
                message="HTTP loads directly without redirect to HTTPS",
                severity=Severity.CRITICAL,
                score_impact=-15,
                recommendation="Configure 301 redirect from HTTP to HTTPS",
                data=http_redirect,
            )]
        
        if cert_error:
            return [self._create_result(
                passed=False,
                message="HTTPS endpoint has certificate error",
                severity=Severity.CRITICAL,
                score_impact=-15,
                recommendation="Fix SSL certificate on HTTPS endpoint",
                data=http_redirect,
            )]
        
        if not final_url.startswith("https://"):
            return [self._create_result(
                passed=False,
                message=f"Final URL is not HTTPS: {final_url}",
                severity=Severity.CRITICAL,
                score_impact=-15,
                recommendation="Ensure all traffic redirects to HTTPS",
                data=http_redirect,
            )]
        
        if not is_permanent:
            return [self._create_result(
                passed=False,
                message="HTTP→HTTPS redirect is not permanent (not 301/308)",
                severity=Severity.WARNING,
                score_impact=-5,
                recommendation="Use 301 (Moved Permanently) or 308 (Permanent Redirect)",
                data=http_redirect,
            )]
        
        return [self._create_result(
            passed=True,
            message="HTTP properly redirects to HTTPS with 301/308",
            severity=Severity.PASSED,
            score_impact=0,
            data=http_redirect,
        )]


# ────────────────────────────────────────────────────────────────────────────
# 9. External Links Security (Check #9) - security_013
# ────────────────────────────────────────────────────────────────────────────
class ExternalLinksSecurityRule(BaseRule):
    """Check external links for security attributes."""
    rule_id = "security_013"
    name = "External Links Security"
    category = "security"
    description = "External links should use rel=noopener/noreferrer"
    weight = 1.0
    tags = ["warning", "security", "links"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        links_data = data.get("links", {})
        external_links = links_data.get("external_links", [])
        
        if not external_links:
            return [self._create_result(
                passed=True,
                message="No external links found",
                severity=Severity.PASSED,
                score_impact=0,
            )]
        
        issues = []
        for link in external_links:
            href = link.get("href", "")
            rel = link.get("rel", "").lower() if isinstance(link.get("rel"), str) else ""
            
            if href.startswith("http://"):
                issues.append(f"External HTTP link (downgrade): {href}")
            
            if "noopener" not in rel and "noreferrer" not in rel:
                if link.get("target") == "_blank" or href.startswith("http"):
                    issues.append(f"Missing rel=noopener/noreferrer: {href}")
        
        if issues:
            return [self._create_result(
                passed=False,
                message=f"Found {len(issues)} external link security issues",
                severity=Severity.WARNING,
                score_impact=-3,
                recommendation="Add rel='noopener noreferrer' to external links; use HTTPS for external links",
                data={"issues": issues[:10], "total_external": len(external_links)},
            )]
        
        return [self._create_result(
            passed=True,
            message="All external links have proper security attributes",
            severity=Severity.PASSED,
            score_impact=0,
            data={"total_external": len(external_links)},
        )]


# ────────────────────────────────────────────────────────────────────────────
# 10. Form HTTPS Actions (Check #10) - security_014
# ────────────────────────────────────────────────────────────────────────────
class FormHTTPSActionsRule(BaseRule):
    """Check form actions use HTTPS."""
    rule_id = "security_014"
    name = "Form HTTPS Actions"
    category = "security"
    description = "Forms must submit to HTTPS endpoints"
    weight = 1.4
    tags = ["critical", "security", "forms"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        html = data.get("html", "")
        final_url = data.get("final_url", data.get("url", ""))
        
        if not html:
            return [self._create_result(
                passed=True,
                message="No HTML to analyze",
                severity=Severity.PASSED,
                score_impact=0,
            )]
        
        forms = _extract_form_actions(html, final_url)
        
        if not forms:
            return [self._create_result(
                passed=True,
                message="No forms found",
                severity=Severity.PASSED,
                score_impact=0,
            )]
        
        insecure_forms = []
        for form in forms:
            resolved = form["resolved"]
            if resolved.startswith("http://"):
                insecure_forms.append({
                    "action": form["action"],
                    "resolved": resolved,
                })
        
        if insecure_forms:
            return [self._create_result(
                passed=False,
                message=f"{len(insecure_forms)} form(s) submit to HTTP",
                severity=Severity.CRITICAL,
                score_impact=-15,
                recommendation="Change all form actions to HTTPS",
                data={"insecure_forms": insecure_forms},
            )]
        
        return [self._create_result(
            passed=True,
            message=f"All {len(forms)} form(s) submit to HTTPS",
            severity=Severity.PASSED,
            score_impact=0,
            data={"forms_checked": len(forms)},
        )]


# ────────────────────────────────────────────────────────────────────────────
# 11. Mixed Content (Check #11) - security_002
# ────────────────────────────────────────────────────────────────────────────
class MixedContentRule(BaseRule):
    """Check for mixed content (HTTP resources on HTTPS page)."""
    rule_id = "security_002"
    name = "Mixed Content"
    category = "security"
    description = "HTTPS pages must not load HTTP resources"
    weight = 1.3
    tags = ["critical", "security", "https"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        html = data.get("html", "")
        final_url = data.get("final_url", data.get("url", ""))
        
        if not html or not final_url.startswith("https://"):
            return [self._create_result(
                passed=True,
                message="Page is not HTTPS or no HTML to analyze",
                severity=Severity.PASSED,
                score_impact=0,
            )]
        
        mixed = _extract_mixed_content(html, final_url)
        active = mixed["active"]
        passive = mixed["passive"]
        
        if active:
            return [self._create_result(
                passed=False,
                message=f"Active mixed content: {len(active)} HTTP resource(s) on HTTPS page",
                severity=Severity.CRITICAL,
                score_impact=-15,
                recommendation="Update all scripts, stylesheets, and iframes to HTTPS",
                data={"active_count": len(active), "passive_count": len(passive), "active": active[:5], "passive": passive[:5]},
            )]
        
        if passive:
            return [self._create_result(
                passed=False,
                message=f"Passive mixed content: {len(passive)} HTTP resource(s) on HTTPS page",
                severity=Severity.WARNING,
                score_impact=-5,
                recommendation="Update images and media to HTTPS",
                data={"active_count": 0, "passive_count": len(passive), "passive": passive[:5]},
            )]
        
        return [self._create_result(
            passed=True,
            message="No mixed content detected",
            severity=Severity.PASSED,
            score_impact=0,
        )]


# ────────────────────────────────────────────────────────────────────────────
# 12. No Leaked Secrets (Check #12) - security_015
# ────────────────────────────────────────────────────────────────────────────
class NoLeakedSecretsRule(BaseRule):
    """Check for leaked API keys, tokens, passwords in HTML/headers."""
    rule_id = "security_015"
    name = "No Leaked Secrets"
    category = "security"
    description = "No sensitive credentials in client-accessible content"
    weight = 1.5
    tags = ["critical", "security", "secrets"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        html = data.get("html", "")
        headers = data.get("http", {}).get("headers", {})
        
        findings = _scan_leaked_secrets(html, headers)
        
        if findings:
            critical_types = {"AWS Credentials", "Stripe Secret Key", "API Key", "Secret Key", "Auth Token"}
            critical = [f for f in findings if f["type"] in critical_types]
            
            if critical:
                return [self._create_result(
                    passed=False,
                    message=f"CRITICAL: {len(critical)} leaked secret(s) found",
                    severity=Severity.CRITICAL,
                    score_impact=-20,
                    recommendation="Remove all secrets from client-side code; use environment variables",
                    data={"findings": findings[:5], "critical_count": len(critical)},
                )]
            
            return [self._create_result(
                passed=False,
                message=f"Potential secrets found: {len(findings)} item(s)",
                severity=Severity.WARNING,
                score_impact=-10,
                recommendation="Review and remove any sensitive data from HTML/headers",
                data={"findings": findings[:5]},
            )]
        
        return [self._create_result(
            passed=True,
            message="No leaked secrets detected",
            severity=Severity.PASSED,
            score_impact=0,
        )]


# ────────────────────────────────────────────────────────────────────────────
# 13. No Password Fields on HTTP (Check #13) - security_016
# ────────────────────────────────────────────────────────────────────────────
class NoPasswordFieldsOnHTTPRule(BaseRule):
    """Check for password fields on HTTP pages."""
    rule_id = "security_016"
    name = "Password Fields on HTTP"
    category = "security"
    description = "Login forms must not be served over HTTP"
    weight = 1.5
    tags = ["critical", "security", "forms", "http"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        html = data.get("html", "")
        final_url = data.get("final_url", data.get("url", ""))
        
        if not html:
            return [self._create_result(
                passed=True,
                message="No HTML to analyze",
                severity=Severity.PASSED,
                score_impact=0,
            )]
        
        if _has_password_field_on_http(html, final_url):
            return [self._create_result(
                passed=False,
                message="Password field found on HTTP page - credentials sent in plaintext!",
                severity=Severity.CRITICAL,
                score_impact=-20,
                recommendation="Serve all pages with password fields over HTTPS",
                data={"final_url": final_url},
            )]
        
        return [self._create_result(
            passed=True,
            message="No password fields on HTTP",
            severity=Severity.PASSED,
            score_impact=0,
        )]


# ────────────────────────────────────────────────────────────────────────────
# 14. No Protocol-Relative URLs (Check #14) - security_017
# ────────────────────────────────────────────────────────────────────────────
class NoProtocolRelativeURLsRule(BaseRule):
    """Check for protocol-relative URLs (//...)."""
    rule_id = "security_017"
    name = "No Protocol-Relative URLs"
    category = "security"
    description = "Avoid // URLs; use explicit https://"
    weight = 0.8
    tags = ["warning", "security", "urls"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        html = data.get("html", "")
        final_url = data.get("final_url", data.get("url", ""))
        
        if not html:
            return [self._create_result(
                passed=True,
                message="No HTML to analyze",
                severity=Severity.PASSED,
                score_impact=0,
            )]
        
        proto_relative = _extract_protocol_relative_urls(html, final_url)
        
        if proto_relative:
            is_http = final_url.startswith("http://")
            
            return [self._create_result(
                passed=False,
                message=f"Found {len(proto_relative)} protocol-relative URL(s)" + (" on HTTP page!" if is_http else ""),
                severity=Severity.WARNING if not is_http else Severity.CRITICAL,
                score_impact=-5 if not is_http else -10,
                recommendation="Replace // URLs with explicit https://",
                data={"protocol_relative_urls": proto_relative[:10], "page_is_http": is_http},
            )]
        
        return [self._create_result(
            passed=True,
            message="No protocol-relative URLs found",
            severity=Severity.PASSED,
            score_impact=0,
        )]


# ────────────────────────────────────────────────────────────────────────────
# Legacy rules (keep for backward compatibility)
# ────────────────────────────────────────────────────────────────────────────
class HTTPSRule(BaseRule):
    """Check HTTPS usage (legacy - use security_001 for redirect check)."""
    rule_id = "security_001_legacy"
    name = "HTTPS (Legacy)"
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


class SSLCertificateRule(BaseRule):
    """Check SSL certificate validity (legacy - use security_007 for TLS config)."""
    rule_id = "security_004"
    name = "SSL Certificate"
    category = "security"
    description = "SSL certificate must be valid and trusted"
    weight = 1.4
    tags = ["critical", "security", "ssl"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        site_security = data.get("site_security") or {}
        tls = site_security.get("tls") if isinstance(site_security, dict) else None
        if not isinstance(tls, dict) or not tls:
            url_info = data.get("url") or {}
            if isinstance(url_info, dict) and url_info.get("https") is False:
                return [self._create_result(
                    passed=True,
                    message="SSL certificate check not applicable; HTTPS usage is checked separately",
                    severity=Severity.INFO,
                    score_impact=0,
                    data={"certificate_status": "not_applicable"},
                )]

            return [self._create_result(
                passed=False,
                message="SSL certificate could not be verified because the TLS probe result is unavailable",
                severity=Severity.WARNING,
                score_impact=0,
                recommendation="Retry the audit TLS probe to verify the certificate",
                data={"certificate_status": "unverified"},
            )]

        error = tls.get("error")
        if error and str(error).startswith("Certificate verification failed:"):
            return [self._create_result(
                passed=False,
                message=f"SSL certificate validation failed: {error}",
                severity=Severity.CRITICAL,
                score_impact=-15,
                recommendation="Fix SSL certificate issues",
                data={"certificate_status": "invalid", "tls": tls},
            )]

        if error:
            return [self._create_result(
                passed=False,
                message=f"SSL certificate could not be verified: {error}",
                severity=Severity.WARNING,
                score_impact=0,
                recommendation="Retry the TLS probe; check certificate validity after connectivity is restored",
                data={"certificate_status": "unverified", "tls": tls},
            )]

        if tls.get("certificate_valid") is not True:
            return [self._create_result(
                passed=False,
                message="SSL certificate validation could not be confirmed",
                severity=Severity.WARNING,
                score_impact=0,
                recommendation="Retry the audit TLS probe to verify the certificate",
                data={"certificate_status": "unverified", "tls": tls},
            )]

        if tls.get("chain_trusted") is not True:
            return [self._create_result(
                passed=False,
                message="SSL certificate chain is not trusted",
                severity=Severity.CRITICAL,
                score_impact=-15,
                recommendation="Install the complete certificate chain from a trusted certificate authority",
                data={"certificate_status": "invalid", "tls": tls},
            )]

        issuer = tls.get("certificate_issuer", "")
        expiry_date = tls.get("certificate_expiry", "")
        return [self._create_result(
            passed=True,
            message=f"Valid SSL certificate from {issuer or 'trusted CA'}",
            severity=Severity.PASSED,
            score_impact=0,
            data={
                "certificate_status": "valid",
                "certificate_valid": True,
                "chain_trusted": True,
                "issuer": issuer,
                "expiry_date": expiry_date,
                "tls": tls,
            },
        )]


class SecurityHeadersRule(BaseRule):
    """Check security headers (legacy - use individual header rules)."""
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


class XSSProtectionRule(BaseRule):
    """Check XSS protection (legacy)."""
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