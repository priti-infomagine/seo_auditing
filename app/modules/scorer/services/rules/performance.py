"""
Performance SEO Rules.
"""
from typing import Any, Dict, List

from app.modules.scorer.services.base_rule import BaseRule
from app.modules.scorer.models.rule_result import RuleResult, Severity


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
                message=f"Large HTML size: {size_kb:.1f}KB",
                severity=Severity.WARNING,
                score_impact=-3,
                recommendation="Reduce HTML size by removing unnecessary code and comments",
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
    description = "Static assets should have cache headers"
    weight = 0.8
    tags = ["warning", "performance", "caching"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        http = data.get("http", {})
        headers = http.get("headers", {})
        
        cache_control = headers.get("cache-control", "")
        expires = headers.get("expires", "")
        
        if cache_control or expires:
            return [self._create_result(
                passed=True,
                message="Cache headers present",
                severity=Severity.PASSED,
                score_impact=0,
                data={"cache_control": cache_control, "expires": expires},
            )]
        
        return [self._create_result(
            passed=False,
            message="No cache headers found",
            severity=Severity.INFO,
            score_impact=-2,
            recommendation="Add Cache-Control and Expires headers for static assets",
        )]


class CompressionRule(BaseRule):
    """Check for gzip/brotli compression."""
    rule_id = "perf_006"
    name = "Compression"
    category = "performance"
    description = "Responses should be compressed"
    weight = 1.0
    tags = ["warning", "performance", "compression"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        http = data.get("http", {})
        headers = http.get("headers", {})
        
        content_encoding = headers.get("content-encoding", "").lower()
        
        if "gzip" in content_encoding or "br" in content_encoding or "deflate" in content_encoding:
            compression_type = "gzip" if "gzip" in content_encoding else "brotli" if "br" in content_encoding else "deflate"
            return [self._create_result(
                passed=True,
                message=f"Compression enabled ({compression_type})",
                severity=Severity.PASSED,
                score_impact=0,
                data={"compression": compression_type},
            )]
        
        return [self._create_result(
            passed=False,
            message="No compression detected",
            severity=Severity.WARNING,
            score_impact=-5,
            recommendation="Enable gzip or brotli compression on your server",
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