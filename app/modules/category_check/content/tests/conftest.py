"""
Conftest for Content crawler pipeline tests.

Provides shared fixtures mirroring core_seo's test conftest, but
uses the content-specific parser and rule data builder.
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
    <p>Good content helps your site rank. Search engines like sites with real text. Short words and simple sentences help users read fast. This page has lots of easy text to test the rules right.</p>
    <p>Keep your pages full of good tips. Tell users what they need to know. Do not make long hard words when a short one works just as well. Simple is better for most readers.</p>
    <p>Use short lines and clear steps. Break big thought into small bits. Each bit is easy to read. This helps users stay on your page and find what they seek.</p>
    <p>Links help users move around. Put them in your best spots. Do not use too many or it gets hard to follow. A few good links are better than a big pile of links.</p>
    <p>Headers make your page clear. Use H1 for the main title. Use H2 for big parts. This helps both users and search bots read your page well.</p>
    <p>Images need text too. Alt text helps the blind and helps search bots. Use words that explain the image. Do not skip this step if you can help it.</p>
    <a href="https://example.com/page-two">Internal Link</a>
    <a href="https://external.com/page">External Link</a>
    <img src="/image.png" alt="Sample image alt text">
    <img src="/image2.png">
</body>
</html>
"""


@pytest.fixture
def sample_html():
    return SAMPLE_HTML


@pytest.fixture
def minimal_html():
    return "<html><head><title>Bad</title></head><body></body></html>"


@pytest.fixture
def content_rule_data(sample_html):
    """Return enriched data dict for content rule evaluation."""
    from app.modules.category_check.content.data_builder import build_content_rule_data
    from app.modules.category_check.content.page_parser import ContentPageParser
    from app.modules.category_check.core_seo.models import CrawlResult

    parser = ContentPageParser()
    html = html_lib.unescape(sample_html)
    parsed = parser.parse(html, "https://example.com/sample-page")
    crawl_result = CrawlResult(
        url="https://example.com/sample-page",
        html=html,
        status_code=200,
        headers={"content-type": "text/html; charset=utf-8"},
        success=True,
    )
    return build_content_rule_data(parsed, crawl_result)


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
