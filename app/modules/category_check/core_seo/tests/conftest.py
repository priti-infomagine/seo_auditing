"""
Conftest for Core SEO crawler pipeline tests.

Provides shared fixtures for rule testing and pipeline testing without
any external dependencies (no DB, no Redis, no real Playwright).
"""
from __future__ import annotations

import html as html_lib

import pytest

from app.modules.category_check.core_seo.constants import (
    BLOCKED_HOSTS,
    BLOCKED_IP_NETWORKS,
    GRADE_THRESHOLDS,
    TRACKING_PARAMS,
)
from app.modules.category_check.core_seo.url_normalizer import URLNormalizer

SAMPLE_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="description" content="A sample page for testing the SEO crawler pipeline. This description is long enough to pass length checks.">
    <meta name="robots" content="index, follow">
    <title>Sample Test Page Title Here For SEO Testing</title>
    <link rel="canonical" href="https://example.com/sample-page">
    <link rel="icon" href="/favicon.ico" type="image/x-icon">
</head>
<body>
    <h1>Main Heading for the Page</h1>
    <h2>Section One</h2>
    <p>This is a paragraph with some content that is long enough to be meaningful for testing purposes. We need to ensure the word count exceeds the minimum threshold.</p>
    <p>Another paragraph of content for the test page. This ensures we have enough text to pass content-based SEO rules.</p>
    <p>Additional paragraph to provide more content. The SEO rules need sufficient content to evaluate properly, and we want to make sure the word count is high enough for testing.</p>
    <p>More text here to ensure adequate word count for SEO evaluation. Content quality matters for search engine optimization, and having enough text is important.</p>
    <a href="https://example.com/page-two">Internal Link</a>
    <a href="https://external.com/page">External Link</a>
    <img src="/image.png" alt="Sample image alt text">
    <img src="/image2.png">
</body>
</html>
"""


@pytest.fixture
def sample_html():
    """Return a comprehensive sample HTML document for testing."""
    return SAMPLE_HTML


@pytest.fixture
def minimal_html():
    """Return a minimal HTML document with several issues."""
    return "<html><head><title>Bad</title></head><body></body></html>"


@pytest.fixture
def rule_data(sample_html):
    """Return rule evaluation data dict (as PageParser.build_rule_data produces)."""
    from app.modules.category_check.core_seo.page_parser import PageParser

    parser = PageParser()
    html = html_lib.unescape(sample_html)
    parsed = parser.parse(html, "https://example.com/sample-page")
    return parser.build_rule_data(parsed)


@pytest.fixture
def url_normalizer():
    return URLNormalizer


@pytest.fixture
def grade_thresholds():
    return GRADE_THRESHOLDS


@pytest.fixture
def blocked_networks():
    return BLOCKED_IP_NETWORKS


@pytest.fixture
def blocked_hosts():
    return BLOCKED_HOSTS


@pytest.fixture
def tracking_params():
    return TRACKING_PARAMS
