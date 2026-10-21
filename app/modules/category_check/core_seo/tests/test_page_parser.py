"""Tests for PageParser."""
from __future__ import annotations

import pytest

from app.modules.category_check.core_seo.page_parser import PageParser


class TestPageParser:
    @pytest.fixture
    def parser(self):
        return PageParser()

    def test_parse_extracts_title(self, parser, sample_html):
        parsed = parser.parse(sample_html, "https://example.com/sample-page")
        assert "Sample Test Page Title" in parsed.title

    def test_parse_extracts_description(self, parser, sample_html):
        parsed = parser.parse(sample_html, "https://example.com/sample-page")
        assert "sample page for testing" in parsed.description

    def test_parse_extracts_canonical(self, parser, sample_html):
        parsed = parser.parse(sample_html, "https://example.com/sample-page")
        assert parsed.canonical == "https://example.com/sample-page"

    def test_parse_extracts_robots_meta(self, parser, sample_html):
        parsed = parser.parse(sample_html, "https://example.com/sample-page")
        assert "index" in parsed.robots_meta
        assert "follow" in parsed.robots_meta

    def test_parse_extracts_viewport(self, parser, sample_html):
        parsed = parser.parse(sample_html, "https://example.com/sample-page")
        assert "width" in parsed.viewport

    def test_parse_extracts_headings(self, parser, sample_html):
        parsed = parser.parse(sample_html, "https://example.com/sample-page")
        assert parsed.heading_counts["h1"] >= 1
        assert "h1" in parsed.headings
        assert len(parsed.headings["h1"]) >= 1

    def test_parse_extracts_robots_nofollow(self, parser):
        html = '<html><head><meta name="robots" content="noindex, nofollow"></head><body></body></html>'
        parsed = parser.parse(html, "https://example.com")
        assert "noindex" in parsed.robots_meta

    def test_parse_extracts_favicon(self, parser, sample_html):
        parsed = parser.parse(sample_html, "https://example.com/sample-page")
        assert len(parsed.favicon_urls) > 0

    def test_parse_no_favicon(self, parser):
        html = '<html><head><title>Test</title></head><body></body></html>'
        parsed = parser.parse(html, "https://example.com")
        assert len(parsed.favicon_urls) == 0

    def test_parse_extracts_links(self, parser, sample_html):
        parsed = parser.parse(sample_html, "https://example.com/sample-page")
        assert len(parsed.links) >= 1
        assert len(parsed.internal_links) >= 1
        assert len(parsed.external_links) >= 1

    def test_parse_extracts_images(self, parser, sample_html):
        parsed = parser.parse(sample_html, "https://example.com/sample-page")
        assert len(parsed.images) >= 1

    def test_parse_word_count(self, parser, sample_html):
        parsed = parser.parse(sample_html, "https://example.com/sample-page")
        assert parsed.word_count > 100

    def test_parse_content_text(self, parser, sample_html):
        parsed = parser.parse(sample_html, "https://example.com/sample-page")
        assert len(parsed.content_text) > 0

    def test_build_rule_data_returns_dict(self, parser, sample_html):
        parsed = parser.parse(sample_html, "https://example.com/sample-page")
        rule_data = parser.build_rule_data(parsed)
        assert isinstance(rule_data, dict)
        assert "title" in rule_data
        assert "description" in rule_data
        assert "url" in rule_data
        assert "canonical" in rule_data
        assert "robots_meta" in rule_data
        assert "viewport" in rule_data
        assert "heading_counts" in rule_data
        assert "favicon_urls" in rule_data

    def test_build_rule_data_canonical_source_count(self, parser, sample_html):
        parsed = parser.parse(sample_html, "https://example.com/sample-page")
        rule_data = parser.build_rule_data(parsed)
        assert "canonical_source_count" in rule_data

    def test_parse_empty_html(self, parser):
        parsed = parser.parse("", "https://example.com")
        assert parsed.title == ""

    def test_parse_invalid_html_no_crash(self, parser):
        html = "<html><head><title>Test</title></head>"
        parsed = parser.parse(html, "https://example.com")
        assert parsed.title == "Test"
