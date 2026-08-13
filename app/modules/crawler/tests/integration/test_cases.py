"""
Test case definitions for the end-to-end crawler test harness.

Each test case specifies:
- url: The URL to crawl
- category: Human-readable category name
- expected_render_mode: "http", "browser", or None (don't care)
- expect_success: Whether the crawl is expected to succeed
- expect_browser_fallback: Whether browser fallback is expected
- description: Brief description of what this test validates
"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass(slots=True)
class CrawlTestCase:
    url: str
    category: str
    expected_render_mode: Optional[str] = None  # "http", "browser", or None
    expect_success: bool = True
    expect_browser_fallback: bool = True
    description: str = ""

    @property
    def normalized_domain(self) -> str:
        from urllib.parse import urlparse
        parsed = urlparse(self.url)
        host = parsed.hostname or parsed.path
        if not host:
            return "invalid"
        # Remove leading www. for cleaner directory names
        if host.startswith("www."):
            host = host[4:]
        return host.lower()


# ---------------------------------------------------------------------------
# URL Test Matrix
# ---------------------------------------------------------------------------
# Diverse set of real public URLs covering:
# - SSR/static HTML
# - CSR/heavy JS
# - Redirects
# - Errors
# - Non-HTML
# - Fragments / query params
# ---------------------------------------------------------------------------

TEST_CASES = [
    # 1. Real business website - normal HTTP/SSR behavior
    CrawlTestCase(
        url="https://www.apple.com",
        category="business_website",
        description="Real business website, test normal HTTP/SSR behavior and SEO extraction",
    ),

    # 2. Complex modern web application - CSR/hybrid behavior
    CrawlTestCase(
        url="https://www.reddit.com",
        category="modern_web_app",
        description="Complex modern web application, test rendering decision",
    ),

    # 3. Simple static/SSR HTML website
    CrawlTestCase(
        url="https://example.com",
        category="static_ssr",
        expected_render_mode="http",
        description="Simple static HTML page, should not trigger Playwright",
    ),

    # 4. Strong HTML document with no reason to use Playwright
    CrawlTestCase(
        url="https://httpbin.org/html",
        category="strong_html",
        expected_render_mode="http",
        description="HTML page with complete document structure, HTTP-only",
    ),

    # 5. JavaScript-heavy/CSR website
    CrawlTestCase(
        url="https://vuejs.org",
        category="javascript_heavy",
        description="JavaScript-heavy site, may trigger browser fallback",
    ),

    # 6. Next.js/React-style website
    CrawlTestCase(
        url="https://nextjs.org",
        category="nextjs_react",
        description="Next.js/React-style website, test rendering decision",
    ),

    # 7. Website with redirects
    CrawlTestCase(
        url="http://github.com",
        category="redirects",
        expected_render_mode="http",
        description="HTTP -> HTTPS redirect chain",
    ),

    # 8. Website with missing/weak SEO metadata
    CrawlTestCase(
        url="https://httpbin.org/status/200",
        category="weak_seo_metadata",
        description="Minimal response, may have weak SEO metadata",
    ),

    # 9. Website with internal and external links
    CrawlTestCase(
        url="https://httpbin.org/links/5/0",
        category="links_test",
        expected_render_mode="http",
        description="Page with known internal/external links",
    ),

    # 10. Website containing images
    CrawlTestCase(
        url="https://example.com",
        category="images",
        expected_render_mode="http",
        description="Page containing images, test asset extraction",
    ),

    # 11. Deliberately invalid URL
    CrawlTestCase(
        url="https://invalid.url.that.does.not.exist.example",
        category="invalid_url",
        expect_success=False,
        description="Invalid domain, should fail gracefully",
    ),

    # 12. Non-HTML URL
    CrawlTestCase(
        url="https://httpbin.org/json",
        category="non_html",
        expected_render_mode="http",
        description="JSON response, should not trigger Playwright",
    ),

    # 13. URL with a fragment
    CrawlTestCase(
        url="https://example.com/#section",
        category="fragment",
        expected_render_mode="http",
        description="URL with fragment identifier",
    ),

    # 14. URL with query parameters
    CrawlTestCase(
        url="https://example.com?utm_source=test&id=1&ref=abc",
        category="query_params",
        expected_render_mode="http",
        description="URL with tracking and non-tracking query parameters",
    ),

    # 15. URL that returns an HTTP error
    CrawlTestCase(
        url="https://httpbin.org/status/404",
        category="http_error",
        expect_success=False,
        description="404 response, should fail gracefully",
    ),
]
