"""
Performance SEO Rules.
"""
from typing import Any, Dict, List

from app.modules.scorer.services.base_rule import BaseRule
from app.modules.rule_engine.models.rule_result import RuleResult, Severity


class ResponseTimeRule(BaseRule):
    """Check server response time."""
    rule_id = "perf_001"
    name = "Response Time"
    category = "performance"
    description = "Server should respond quickly"
    weight = 1.3
    tags = ["critical", "performance", "core_web_vitals"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        http = data.get("http", {})
        response_time = http.get("response_time", 0)
        
        if response_time == 0:
            return [self._create_result(
                passed=True,
                message="Response time not available",
                severity=Severity.INFO,
                score_impact=0,
            )]
        
        response_time_seconds = response_time / 1000 if response_time > 10 else response_time
        
        if response_time_seconds <= 0.2:
            return [self._create_result(
                passed=True,
                message=f"Excellent response time: {response_time_seconds:.2f}s",
                severity=Severity.PASSED,
                score_impact=2,
                data={"response_time": response_time_seconds},
            )]
        
        if response_time_seconds <= 0.5:
            return [self._create_result(
                passed=True,
                message=f"Good response time: {response_time_seconds:.2f}s",
                severity=Severity.PASSED,
                score_impact=0,
                data={"response_time": response_time_seconds},
            )]
        
        if response_time_seconds <= 1.0:
            return [self._create_result(
                passed=False,
                message=f"Slow response time: {response_time_seconds:.2f}s (should be <200ms)",
                severity=Severity.WARNING,
                score_impact=-5,
                recommendation="Optimize server response time to under 200ms",
                data={"response_time": response_time_seconds},
            )]
        
        return [self._create_result(
            passed=False,
            message=f"Very slow response time: {response_time_seconds:.2f}s",
            severity=Severity.CRITICAL,
            score_impact=-10,
            recommendation="Critical: Optimize server, database queries, and caching",
            data={"response_time": response_time_seconds},
        )]


class HTMLSizeRule(BaseRule):
    """Check HTML document size."""
    rule_id = "perf_002"
    name = "HTML Document Size"
    category = "performance"
    description = "HTML should be optimized and compressed"
    weight = 0.9
    tags = ["warning", "performance", "size"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        content = data.get("content", {})
        html_size = content.get("html_size", 0)
        
        if html_size == 0:
            return [self._create_result(
                passed=True,
                message="HTML size not available",
                severity=Severity.INFO,
                score_impact=0,
            )]
        
        size_kb = html_size / 1024
        
        if size_kb <= 50:
            return [self._create_result(
                passed=True,
                message=f"Excellent HTML size: {size_kb:.1f}KB",
                severity=Severity.PASSED,
                score_impact=1,
                data={"html_size_kb": size_kb},
            )]
        
        if size_kb <= 100:
            return [self._create_result(
                passed=True,
                message=f"Good HTML size: {size_kb:.1f}KB",
                severity=Severity.PASSED,
                score_impact=0,
                data={"html_size_kb": size_kb},
            )]
        
        if size_kb <= 200:
            return [self._create_result(
                passed=False,
                message=f"HTML size exceeds 100KB: {size_kb:.1f}KB",
                severity=Severity.WARNING,
                score_impact=-3,
                recommendation="Reduce HTML size - aim for under 100KB",
                data={"html_size_kb": size_kb},
            )]
        
        return [self._create_result(
            passed=False,
            message=f"Very large HTML size: {size_kb:.1f}KB",
            severity=Severity.WARNING,
            score_impact=-5,
            recommendation="Critical: Reduce HTML size - consider code splitting and minification",
            data={"html_size_kb": size_kb},
        )]


class MinificationRule(BaseRule):
    """Check for HTML/CSS/JS minification."""
    rule_id = "perf_003"
    name = "Code Minification"
    category = "performance"
    description = "HTML, CSS, and JS should be minified"
    weight = 0.8
    tags = ["info", "performance", "optimization"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        performance = data.get("performance", {})
        minification = performance.get("minification", {})
        
        if not minification:
            return [self._create_result(
                passed=True,
                message="Minification check not available",
                severity=Severity.INFO,
                score_impact=0,
                recommendation="Enable HTML/CSS/JS minification for better performance",
            )]
        
        html_minified = minification.get("html_minified", False)
        css_minified = minification.get("css_minified", False)
        js_minified = minification.get("js_minified", False)
        
        if html_minified and css_minified and js_minified:
            return [self._create_result(
                passed=True,
                message="All code is minified",
                severity=Severity.PASSED,
                score_impact=1,
                data={"html": True, "css": True, "js": True},
            )]
        
        minified_count = sum([html_minified, css_minified, js_minified])
        return [self._create_result(
            passed=False,
            message=f"Minification incomplete ({minified_count}/3 types minified)",
            severity=Severity.INFO,
            score_impact=-2,
            recommendation="Minify HTML, CSS, and JavaScript files",
            data={"html": html_minified, "css": css_minified, "js": js_minified},
        )]


class ResourceCountRule(BaseRule):
    """Check number of resources (CSS, JS, images)."""
    rule_id = "perf_004"
    name = "Resource Count"
    category = "performance"
    description = "Too many resources can slow down page load"
    weight = 0.9
    tags = ["warning", "performance", "resources"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        performance = data.get("performance", {})
        resources = performance.get("resources", {})
        
        if not resources:
            return [self._create_result(
                passed=True,
                message="Resource count not available",
                severity=Severity.INFO,
                score_impact=0,
            )]
        
        css_count = resources.get("css", 0)
        js_count = resources.get("javascript", 0)
        image_count = resources.get("images", 0)
        total_resources = css_count + js_count + image_count
        
        if total_resources <= 20:
            return [self._create_result(
                passed=True,
                message=f"Good resource count: {total_resources} resources",
                severity=Severity.PASSED,
                score_impact=0,
                data={"total": total_resources, "css": css_count, "js": js_count, "images": image_count},
            )]
        
        
        if total_resources <= 50:
            return [self._create_result(
                passed=False,
                message=f"Many resources: {total_resources} (CSS: {css_count}, JS: {js_count}, Images: {image_count})",
                severity=Severity.WARNING,
                score_impact=-3,
                recommendation="Reduce number of resources - combine files and use sprites",
                data={"total": total_resources, "css": css_count, "js": js_count, "images": image_count},
            )]
        
        return [self._create_result(
            passed=False,
            message=f"Too many resources: {total_resources} (CSS: {css_count}, JS: {js_count}, Images: {image_count})",
            severity=Severity.WARNING,
            score_impact=-6,
            recommendation="Critical: Reduce HTTP requests by bundling and minifying resources",
            data={"total": total_resources, "css": css_count, "js": js_count, "images": image_count},
        )]


class CacheHeadersRule(BaseRule):
    """Check for browser caching headers."""
    rule_id = "perf_005"
    name = "Browser Caching"
    category = "performance"
    description = "Static assets should have cache headers with appropriate max-age"
    weight = 0.8
    tags = ["warning", "performance", "caching"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        http = data.get("http", {})
        headers = http.get("headers", {})
        
        cache_control = headers.get("cache-control", "")
        expires = headers.get("expires", "")
        
        if not cache_control and not expires:
            return [self._create_result(
                passed=False,
                message="No cache headers found",
                severity=Severity.INFO,
                score_impact=-2,
                recommendation="Add Cache-Control and Expires headers for static assets",
            )]
        
        # Parse max-age from cache-control
        max_age = 0
        if "max-age=" in cache_control:
            try:
                max_age = int(cache_control.split("max-age=")[1].split(",")[0].strip())
            except (ValueError, IndexError):
                pass
        
        if max_age >= 31536000:  # 1 year
            return [self._create_result(
                passed=True,
                message=f"Excellent cache policy (max-age: {max_age}s)",
                severity=Severity.PASSED,
                score_impact=1,
                data={"cache_control": cache_control, "expires": expires, "max_age": max_age},
            )]
        
        if max_age >= 86400:  # 1 day
            return [self._create_result(
                passed=True,
                message=f"Good cache headers (max-age: {max_age}s)",
                severity=Severity.PASSED,
                score_impact=0,
                data={"cache_control": cache_control, "expires": expires, "max_age": max_age},
            )]
        
        if max_age > 0:
            return [self._create_result(
                passed=False,
                message=f"Short cache max-age: {max_age}s (recommend ≥1 day)",
                severity=Severity.WARNING,
                score_impact=-1,
                recommendation="Increase cache max-age to at least 1 day (86400s)",
                data={"cache_control": cache_control, "expires": expires, "max_age": max_age},
            )]
        
        return [self._create_result(
            passed=True,
            message="Cache headers present but no max-age",
            severity=Severity.INFO,
            score_impact=-1,
            data={"cache_control": cache_control, "expires": expires},
        )]


class CompressionRule(BaseRule):
    """Check for gzip/brotli compression."""
    rule_id = "perf_006"
    name = "Compression"
    category = "performance"
    description = "Responses should be compressed with gzip or brotli"
    weight = 1.0
    tags = ["warning", "performance", "compression"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        http = data.get("http", {})
        headers = http.get("headers", {})
        
        content_encoding = headers.get("content-encoding", "").lower()
        
        has_gzip = "gzip" in content_encoding
        has_brotli = "br" in content_encoding
        has_deflate = "deflate" in content_encoding
        has_compression = has_gzip or has_brotli or has_deflate
        
        if not has_compression:
            return [self._create_result(
                passed=False,
                message="No text compression detected (gzip, brotli, or deflate)",
                severity=Severity.WARNING,
                score_impact=-5,
                recommendation="Enable gzip or brotli compression on your server",
            )]
        
        # Determine compression type and quality
        compression_types = []
        if has_brotli:
            compression_types.append("brotli")
        if has_gzip:
            compression_types.append("gzip")
        if has_deflate:
            compression_types.append("deflate")
        
        # Prefer brotli > gzip > deflate
        if has_brotli:
            severity = Severity.PASSED
            impact = 1
            msg = "Excellent: Brotli compression enabled"
        elif has_gzip:
            severity = Severity.PASSED
            impact = 0
            msg = "Good: Gzip compression enabled"
        else:
            severity = Severity.WARNING
            impact = -2
            msg = "Compression enabled (deflate - consider upgrading to gzip/brotli)"
        
        return [self._create_result(
            passed=True,
            message=msg,
            severity=severity,
            score_impact=impact,
            data={"compression_types": compression_types},
        )]


class BrotliCompressionRule(BaseRule):
    """Check specifically for Brotli compression (best modern compression)."""
    rule_id = "perf_014"
    name = "Brotli Compression"
    category = "performance"
    description = "Responses should use Brotli compression for optimal performance"
    weight = 0.8
    tags = ["info", "performance", "compression"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        http = data.get("http", {})
        headers = http.get("headers", {})
        
        content_encoding = headers.get("content-encoding", "").lower()
        
        if "br" in content_encoding:
            return [self._create_result(
                passed=True,
                message="Brotli compression enabled (optimal)",
                severity=Severity.PASSED,
                score_impact=1,
                data={"compression": "brotli"},
            )]
        
        return [self._create_result(
            passed=False,
            message="Brotli compression not detected - consider upgrading from gzip",
            severity=Severity.INFO,
            score_impact=-1,
            recommendation="Configure server to use Brotli compression for better compression ratios",
            data={"current_encoding": content_encoding},
        )]


class PageSizeRule(BaseRule):
    """Check total page size."""
    rule_id = "perf_007"
    name = "Total Page Size"
    category = "performance"
    description = "Total page size should be under 2MB"
    weight = 1.0
    tags = ["warning", "performance", "size"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        performance = data.get("performance", {})
        page_size = performance.get("total_size", 0)
        
        if page_size == 0:
            return [self._create_result(
                passed=True,
                message="Page size not available",
                severity=Severity.INFO,
                score_impact=0,
            )]
        
        size_mb = page_size / (1024 * 1024)
        
        if size_mb <= 1.0:
            return [self._create_result(
                passed=True,
                message=f"Excellent page size: {size_mb:.2f}MB",
                severity=Severity.PASSED,
                score_impact=1,
                data={"size_mb": size_mb},
            )]
        
        if size_mb <= 2.0:
            return [self._create_result(
                passed=False,
                message=f"Page size is {size_mb:.2f}MB (recommended: <2MB)",
                severity=Severity.WARNING,
                score_impact=-3,
                recommendation="Reduce page size by optimizing images and removing unused code",
                data={"size_mb": size_mb},
            )]
        
        return [self._create_result(
            passed=False,
            message=f"Page is too large: {size_mb:.2f}MB",
            severity=Severity.WARNING,
            score_impact=-6,
            recommendation="Critical: Reduce page size - aim for under 2MB",
            data={"size_mb": size_mb},
        )]


class JavaScriptErrorsRule(BaseRule):
    """Check for JavaScript errors."""
    rule_id = "perf_008"
    name = "JavaScript Errors"
    category = "performance"
    description = "Page should not have JavaScript errors"
    weight = 1.1
    tags = ["critical", "performance", "javascript"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        javascript = data.get("javascript", {})
        
        if not javascript:
            return [self._create_result(
                passed=True,
                message="JavaScript error check not available",
                severity=Severity.INFO,
                score_impact=0,
            )]
        
        errors = javascript.get("errors", [])
        error_count = len(errors) if errors else 0
        
        if error_count == 0:
            return [self._create_result(
                passed=True,
                message="No JavaScript errors detected",
                severity=Severity.PASSED,
                score_impact=0,
            )]
        
        impact = -min(error_count * 2, 10)
        return [self._create_result(
            passed=False,
            message=f"{error_count} JavaScript errors detected",
            severity=Severity.CRITICAL if error_count > 5 else Severity.WARNING,
            score_impact=impact,
            recommendation="Fix JavaScript errors to ensure proper page functionality",
            data={"error_count": error_count, "errors": errors[:5]},
        )]


class CoreWebVitalsRule(BaseRule):
    """Check Core Web Vitals (LCP, INP, CLS)."""
    rule_id = "core_web_vitals_001"
    name = "Core Web Vitals"
    category = "performance"
    description = "Measure Core Web Vitals performance"
    weight = 1.0
    tags = ["warning", "performance", "core_web_vitals"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        cwv = data.get("core_web_vitals", {})
        
        if not cwv:
            return [self._create_result(
                passed=True,
                message="Core Web Vitals not available (requires browser measurement)",
                severity=Severity.INFO,
                score_impact=0,
            )]
        
        lcp = cwv.get("lcp")
        inp = cwv.get("inp")
        cls = cwv.get("cls")
        
        issues = []
        impacts = 0
        details = {"lcp": lcp, "inp": inp, "cls": cls}
        
        if lcp is not None:
            if lcp > 4.0:
                issues.append(f"LCP poor ({lcp:.2f}s)")
                impacts -= 3
            elif lcp > 2.5:
                issues.append(f"LCP needs improvement ({lcp:.2f}s)")
                impacts -= 1
        
        if inp is not None:
            if inp > 500:
                issues.append(f"INP poor ({inp:.0f}ms)")
                impacts -= 3
            elif inp > 200:
                issues.append(f"INP needs improvement ({inp:.0f}ms)")
                impacts -= 1
        
        if cls is not None:
            if cls > 0.25:
                issues.append(f"CLS poor ({cls:.3f})")
                impacts -= 3
            elif cls > 0.1:
                issues.append(f"CLS needs improvement ({cls:.3f})")
                impacts -= 1
        
        if not issues:
            return [self._create_result(
                passed=True,
                message="Core Web Vitals are good",
                severity=Severity.PASSED,
                score_impact=0,
                data=details,
            )]
        
        return [self._create_result(
            passed=False,
            message=f"Core Web Vitals issues: {', '.join(issues)}",
            severity=Severity.WARNING if impacts > -6 else Severity.CRITICAL,
            score_impact=impacts,
            recommendation="Improve Core Web Vitals: optimize LCP, INP, and CLS",
            data=details,
        )]


# =============================================================================
# NEW PERFORMANCE RULES (12 rules)
# =============================================================================

class PreconnectHintsRule(BaseRule):
    """Check for preconnect and dns-prefetch hints."""
    rule_id = "perf_009"
    name = "Preconnect Hints"
    category = "performance"
    description = "Critical third-party origins should use preconnect/dns-prefetch"
    weight = 1.0
    tags = ["warning", "performance", "resource_hints"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        # Prefer rendered data when available
        head = data.get("head_rendered") or data.get("head", {})
        preconnect = head.get("preconnect_hints", [])
        dns_prefetch = head.get("dns_prefetch_hints", [])
        
        if not preconnect and not dns_prefetch:
            return [self._create_result(
                passed=False,
                message="No preconnect or dns-prefetch hints found",
                severity=Severity.WARNING,
                score_impact=-3,
                recommendation="Add <link rel='preconnect'> for critical third-party origins (fonts, CDN, APIs)",
            )]
        
        return [self._create_result(
            passed=True,
            message=f"Found {len(preconnect)} preconnect, {len(dns_prefetch)} dns-prefetch hints",
            severity=Severity.PASSED,
            score_impact=1,
            data={"preconnect": len(preconnect), "dns_prefetch": len(dns_prefetch)},
        )]


class FontLoadingOptimizationRule(BaseRule):
    """Check Google Fonts loading optimization."""
    rule_id = "perf_010"
    name = "Font Loading Optimization"
    category = "performance"
    description = "Google Fonts should use display=swap and font preload"
    weight = 1.0
    tags = ["warning", "performance", "fonts"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        head = data.get("head_rendered") or data.get("head", {})
        google_fonts = head.get("google_fonts_urls", [])
        preload_hints = head.get("preload_hints", [])
        
        if not google_fonts:
            return [self._create_result(
                passed=True,
                message="No Google Fonts detected",
                severity=Severity.INFO,
                score_impact=0,
            )]
        
        issues = []
        for gf in google_fonts:
            href = gf.get("href", "")
            if "display=swap" not in href and "display=optional" not in href and "display=fallback" not in href:
                issues.append(f"Missing display=swap: {href}")
        
        font_preloads = [p for p in preload_hints if p.get("as") == "font"]
        if not font_preloads:
            issues.append("No font preload hints found")
        
        if not issues:
            return [self._create_result(
                passed=True,
                message="Google Fonts optimized (display=swap + preload)",
                severity=Severity.PASSED,
                score_impact=1,
            )]
        
        return [self._create_result(
            passed=False,
            message=f"Font loading issues: {'; '.join(issues)}",
            severity=Severity.WARNING,
            score_impact=-3,
            recommendation="Add display=swap to Google Fonts URLs and preload critical fonts",
            data={"issues": issues, "google_fonts_count": len(google_fonts)},
        )]


class LCPOptimizationRule(BaseRule):
    """Check LCP optimization (static heuristic using rendered HTML)."""
    rule_id = "perf_011"
    name = "LCP Optimization"
    category = "performance"
    description = "Largest Contentful Paint candidate should have fetchpriority=high and preload"
    weight = 1.2
    tags = ["critical", "performance", "lcp", "core_web_vitals"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        images = data.get("images_rendered") or data.get("images", [])
        preload_hints = (data.get("head_rendered") or data.get("head", {})).get("preload_hints", [])
        
        # Find LCP candidates: images with fetchpriority=high or preloaded with fetchpriority=high
        lcp_candidates = []
        for img in images:
            if img.get("fetchpriority") == "high":
                lcp_candidates.append({"type": "img", "url": img.get("url"), "fetchpriority": "high"})
        
        for pl in preload_hints:
            if pl.get("as") == "image" and pl.get("fetchpriority") == "high":
                lcp_candidates.append({"type": "preload", "url": pl.get("href")})
        
        if not lcp_candidates:
            return [self._create_result(
                passed=False,
                message="No LCP optimization detected (missing fetchpriority=high/preload)",
                severity=Severity.WARNING,
                score_impact=-5,
                recommendation="Add fetchpriority='high' to hero image and preload LCP image",
            )]
        
        return [self._create_result(
            passed=True,
            message=f"LCP optimization detected ({len(lcp_candidates)} candidates)",
            severity=Severity.PASSED,
            score_impact=1,
            data={"lcp_candidates": lcp_candidates},
        )]


class MinifyInlineCSSRule(BaseRule):
    """Check inline CSS minification."""
    rule_id = "perf_015"
    name = "Minify Inline CSS"
    category = "performance"
    description = "Inline <style> blocks should be minified"
    weight = 0.8
    tags = ["info", "performance", "minification"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        inline_css = data.get("inline_css_rendered") or data.get("inline_css", [])
        if not inline_css:
            return [self._create_result(
                passed=True,
                message="No inline CSS found",
                severity=Severity.INFO,
                score_impact=0,
            )]
        
        unminified = [css for css in inline_css if not css.get("is_minified", False)]
        if not unminified:
            return [self._create_result(
                passed=True,
                message=f"All {len(inline_css)} inline CSS blocks minified",
                severity=Severity.PASSED,
                score_impact=1,
            )]
        
        total_whitespace = sum(css.get("whitespace_percentage", 0) for css in unminified)
        return [self._create_result(
            passed=False,
            message=f"{len(unminified)} inline CSS block(s) not minified (avg {total_whitespace/len(unminified):.0f}% whitespace)",
            severity=Severity.INFO,
            score_impact=-2,
            recommendation="Minify inline CSS blocks to reduce HTML size",
            data={"unminified_count": len(unminified), "total_blocks": len(inline_css)},
        )]


class HTTP2SupportRule(BaseRule):
    """Check HTTP/2 or HTTP/3 support."""
    rule_id = "perf_016"
    name = "HTTP/2+ Support"
    category = "performance"
    description = "Server should support HTTP/2 or HTTP/3"
    weight = 0.8
    tags = ["info", "performance", "protocol"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        http = data.get("http", {})
        headers = http.get("headers", {})
        
        alt_svc = headers.get("alt-svc", "").lower()
        http_version = http.get("http_version", "").lower()
        
        if "h3" in alt_svc or "h3-" in alt_svc:
            return [self._create_result(
                passed=True,
                message="HTTP/3 (QUIC) supported via alt-svc",
                severity=Severity.PASSED,
                score_impact=1,
                data={"alt_svc": alt_svc},
            )]
        
        if "h2" in alt_svc or http_version in ["2", "2.0", "h2"]:
            return [self._create_result(
                passed=True,
                message="HTTP/2 supported",
                severity=Severity.PASSED,
                score_impact=0,
                data={"http_version": http_version, "alt_svc": alt_svc},
            )]
        
        return [self._create_result(
            passed=False,
            message="HTTP/2 or HTTP/3 not detected",
            severity=Severity.INFO,
            score_impact=-1,
            recommendation="Enable HTTP/2 or HTTP/3 on your server for better multiplexing",
            data={"http_version": http_version, "alt_svc": alt_svc},
        )]


class DOMSizeRule(BaseRule):
    """Check DOM element count."""
    rule_id = "perf_017"
    name = "DOM Size"
    category = "performance"
    description = "DOM should have fewer than 1500 elements"
    weight = 0.9
    tags = ["warning", "performance", "dom"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        technical = data.get("technical_rendered") or data.get("technical", {})
        dom_count = technical.get("dom_elements", 0)
        
        if dom_count == 0:
            return [self._create_result(
                passed=True,
                message="DOM size not available",
                severity=Severity.INFO,
                score_impact=0,
            )]
        
        if dom_count <= 800:
            return [self._create_result(
                passed=True,
                message=f"Good DOM size: {dom_count} elements",
                severity=Severity.PASSED,
                score_impact=1,
                data={"dom_elements": dom_count},
            )]
        
        if dom_count <= 1500:
            return [self._create_result(
                passed=False,
                message=f"DOM size moderate: {dom_count} elements (recommended: <800)",
                severity=Severity.WARNING,
                score_impact=-2,
                recommendation="Reduce DOM complexity - remove unnecessary wrapper elements",
                data={"dom_elements": dom_count},
            )]
        
        if dom_count <= 3000:
            return [self._create_result(
                passed=False,
                message=f"Large DOM: {dom_count} elements",
                severity=Severity.WARNING,
                score_impact=-5,
                recommendation="Reduce DOM size significantly - consider virtual scrolling or pagination",
                data={"dom_elements": dom_count},
            )]
        
        return [self._create_result(
            passed=False,
            message=f"Very large DOM: {dom_count} elements (critical)",
            severity=Severity.CRITICAL,
            score_impact=-10,
            recommendation="Critical: DOM size severely impacts rendering performance",
            data={"dom_elements": dom_count},
        )]


class RenderBlockingResourcesRule(BaseRule):
    """Check for render-blocking resources."""
    rule_id = "perf_018"
    name = "Render-Blocking Resources"
    category = "performance"
    description = "Critical CSS/JS should not block rendering"
    weight = 1.1
    tags = ["critical", "performance", "render_blocking"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        resources = data.get("resources_rendered") or data.get("resources", [])
        
        blocking_scripts = []
        blocking_styles = []
        
        for res in resources:
            if res.get("resource_type") == "script":
                if not res.get("async_attr") and not res.get("defer_attr") and not res.get("module_attr"):
                    blocking_scripts.append(res.get("url", ""))
            elif res.get("resource_type") == "stylesheet":
                media = res.get("media", "").lower()
                if not media or media == "all" or "screen" in media:
                    blocking_styles.append(res.get("url", ""))
        
        issues = []
        if blocking_scripts:
            issues.append(f"{len(blocking_scripts)} blocking script(s)")
        if blocking_styles:
            issues.append(f"{len(blocking_styles)} blocking stylesheet(s)")
        
        if not issues:
            return [self._create_result(
                passed=True,
                message="No render-blocking resources detected",
                severity=Severity.PASSED,
                score_impact=1,
            )]
        
        return [self._create_result(
            passed=False,
            message=f"Render-blocking resources: {', '.join(issues)}",
            severity=Severity.CRITICAL if blocking_scripts else Severity.WARNING,
            score_impact=-8 if blocking_scripts else -5,
            recommendation="Add async/defer to non-critical scripts, inline critical CSS, defer non-critical CSS",
            data={"blocking_scripts": blocking_scripts[:5], "blocking_styles": blocking_styles[:5]},
        )]


class LazyLoadingAboveFoldRule(BaseRule):
    """Check for lazy loading above fold."""
    rule_id = "perf_019"
    name = "Lazy Loading Above Fold"
    category = "performance"
    description = "Above-fold images should not use loading=lazy without fetchpriority=high"
    weight = 1.0
    tags = ["warning", "performance", "lazy_loading"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        images = data.get("images_rendered") or data.get("images", [])
        
        lazy_above_fold = []
        for img in images:
            loading = img.get("loading", "").lower()
            fetchpriority = img.get("fetchpriority", "").lower()
            
            if loading == "lazy" and fetchpriority != "high":
                lazy_above_fold.append(img.get("url", ""))
        
        if not lazy_above_fold:
            return [self._create_result(
                passed=True,
                message="No lazy-loaded images without fetchpriority=high",
                severity=Severity.PASSED,
                score_impact=0,
            )]
        
        return [self._create_result(
            passed=False,
            message=f"{len(lazy_above_fold)} image(s) with loading=lazy but no fetchpriority=high",
            severity=Severity.WARNING,
            score_impact=-3,
            recommendation="Add fetchpriority='high' to above-fold lazy images or remove lazy loading",
            data={"lazy_images": lazy_above_fold[:5]},
        )]


class CSSFileSizeRule(BaseRule):
    """Check CSS file sizes."""
    rule_id = "perf_020"
    name = "CSS File Size"
    category = "performance"
    description = "CSS files should be under 50KB each"
    weight = 0.8
    tags = ["info", "performance", "css", "size"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        resources = data.get("resources_rendered") or data.get("resources", [])
        stylesheets = [r for r in resources if r.get("resource_type") == "stylesheet"]
        
        if not stylesheets:
            return [self._create_result(
                passed=True,
                message="No stylesheets found",
                severity=Severity.INFO,
                score_impact=0,
            )]
        
        large_css = []
        total_kb = 0
        for css in stylesheets:
            size_kb = css.get("size_kb", 0)
            total_kb += size_kb
            if size_kb > 50:
                large_css.append({"url": css.get("url", ""), "size_kb": size_kb})
        
        if not large_css:
            return [self._create_result(
                passed=True,
                message=f"All {len(stylesheets)} CSS files under 50KB (total: {total_kb:.1f}KB)",
                severity=Severity.PASSED,
                score_impact=0,
                data={"total_kb": round(total_kb, 1), "count": len(stylesheets)},
            )]
        
        return [self._create_result(
            passed=False,
            message=f"{len(large_css)} CSS file(s) over 50KB",
            severity=Severity.WARNING,
            score_impact=-3,
            recommendation="Split large CSS files, remove unused CSS, enable compression",
            data={"large_css": large_css[:5], "total_kb": round(total_kb, 1)},
        )]


class MinifyInlineJSRule(BaseRule):
    """Check inline JavaScript minification."""
    rule_id = "perf_022"
    name = "Minify Inline JS"
    category = "performance"
    description = "Inline <script> blocks should be minified"
    weight = 0.8
    tags = ["info", "performance", "minification"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        inline_js = data.get("inline_js_rendered") or data.get("inline_js", [])
        if not inline_js:
            return [self._create_result(
                passed=True,
                message="No inline JavaScript found",
                severity=Severity.INFO,
                score_impact=0,
            )]
        
        unminified = [js for js in inline_js if not js.get("is_minified", False)]
        if not unminified:
            return [self._create_result(
                passed=True,
                message=f"All {len(inline_js)} inline JS blocks minified",
                severity=Severity.PASSED,
                score_impact=1,
            )]
        
        return [self._create_result(
            passed=False,
            message=f"{len(unminified)} inline JS block(s) not minified",
            severity=Severity.INFO,
            score_impact=-2,
            recommendation="Minify inline JavaScript blocks",
            data={"unminified_count": len(unminified), "total_blocks": len(inline_js)},
        )]


class InlineJSSizeRule(BaseRule):
    """Check inline JavaScript size."""
    rule_id = "perf_023"
    name = "Inline JS Size"
    category = "performance"
    description = "Inline JavaScript should be minimal"
    weight = 0.7
    tags = ["info", "performance", "javascript", "size"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        inline_js = data.get("inline_js_rendered") or data.get("inline_js", [])
        if not inline_js:
            return [self._create_result(
                passed=True,
                message="No inline JavaScript",
                severity=Severity.INFO,
                score_impact=0,
            )]
        
        total_kb = sum(js.get("size_kb", 0) for js in inline_js)
        large_js = [js for js in inline_js if js.get("size_kb", 0) > 10]
        
        if total_kb <= 5 and not large_js:
            return [self._create_result(
                passed=True,
                message=f"Inline JS size optimal: {total_kb:.1f}KB total",
                severity=Severity.PASSED,
                score_impact=0,
                data={"total_kb": round(total_kb, 1)},
            )]
        
        return [self._create_result(
            passed=False,
            message=f"Inline JS size: {total_kb:.1f}KB total ({len(large_js)} block(s) >10KB)",
            severity=Severity.INFO,
            score_impact=-2,
            recommendation="Move inline JavaScript to external files, minify, and defer",
            data={"total_kb": round(total_kb, 1), "large_blocks": len(large_js)},
        )]


class VideoInsteadOfGIFRule(BaseRule):
    """Check for animated GIFs that should be videos."""
    rule_id = "perf_024"
    name = "Video Instead of GIF"
    category = "performance"
    description = "Animated GIFs should use video formats (MP4/WebM)"
    weight = 0.7
    tags = ["info", "performance", "images", "gif"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        images = data.get("images_rendered") or data.get("images", [])
        gifs = [img for img in images if img.get("is_gif", False)]
        
        if not gifs:
            return [self._create_result(
                passed=True,
                message="No animated GIFs detected",
                severity=Severity.PASSED,
                score_impact=0,
            )]
        
        return [self._create_result(
            passed=False,
            message=f"{len(gifs)} animated GIF(s) detected - consider MP4/WebM",
            severity=Severity.INFO,
            score_impact=-2,
            recommendation="Convert animated GIFs to MP4/WebM for 90%+ size reduction",
            data={"gif_count": len(gifs), "gif_urls": [g.get("url", "") for g in gifs[:5]]},
        )]