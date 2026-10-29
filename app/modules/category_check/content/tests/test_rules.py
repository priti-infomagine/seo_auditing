"""Tests for Content rules — all 13 checks."""
from __future__ import annotations

import pytest

from app.modules.category_check.content.rules.base import BaseRule
from app.modules.category_check.content.rules.checks import (
    BrokenHTMLStructureRule,
    ContentMimeTypeRule,
    ContentReadingLevelRule,
    ContentWordCountRule,
    HeadingHierarchyRule,
    HeadingLengthRule,
    KeywordStuffingRule,
    LinkDensityRule,
    MetaDescriptionPixelWidthRule,
    MetaTagsInBodyRule,
    TextToHTMLRatioRule,
    TitleH1DuplicationRule,
    TitlePixelWidthRule,
)
from app.modules.category_check.content.rules.registry import (
    ALL_CONTENT_RULES,
    CONTENT_RULE_COUNT,
    ContentRuleRegistry,
    default_content_registry,
)


class TestTextToHTMLRatioRule:
    def test_pass_good_ratio(self, content_rule_data):
        rule = TextToHTMLRatioRule()
        results = rule.evaluate(content_rule_data)
        assert len(results) == 1
        assert results[0].passed is True

    def test_fail_low_ratio(self):
        rule = TextToHTMLRatioRule()
        results = rule.evaluate({"text_to_html_ratio": 0.05})
        assert len(results) == 1
        assert results[0].passed is False
        assert results[0].severity == "warning"

    def test_rule_id(self):
        rule = TextToHTMLRatioRule()
        assert rule.rule_id == "text_html_ratio"


class TestContentWordCountRule:
    def test_pass_good_count(self, content_rule_data):
        rule = ContentWordCountRule()
        results = rule.evaluate(content_rule_data)
        assert results[0].passed is True

    def test_fail_low_count(self):
        rule = ContentWordCountRule()
        results = rule.evaluate({"word_count": 50})
        assert results[0].passed is False

    def test_rule_id(self):
        rule = ContentWordCountRule()
        assert rule.rule_id == "content_word_count"


class TestLinkDensityRule:
    def test_pass_low_density(self, content_rule_data):
        rule = LinkDensityRule()
        results = rule.evaluate(content_rule_data)
        assert results[0].passed is True

    def test_fail_high_density(self):
        rule = LinkDensityRule()
        results = rule.evaluate({
            "links": [{"text": "a" * 200} for _ in range(10)],
            "content_text": "short text " * 10,
        })
        assert results[0].passed is False

    def test_rule_id(self):
        rule = LinkDensityRule()
        assert rule.rule_id == "link_density"


class TestContentReadingLevelRule:
    def test_pass_simple_text(self, content_rule_data):
        rule = ContentReadingLevelRule()
        results = rule.evaluate(content_rule_data)
        assert results[0].passed is True

    def test_fail_complex_text(self):
        rule = ContentReadingLevelRule()
        # Text with many syllables per word = higher grade
        complex_text = "antidisestablishment " * 100
        results = rule.evaluate({"reading_grade": 12.5})
        assert len(results) == 1
        assert results[0].passed is False

    def test_no_grade_available(self):
        rule = ContentReadingLevelRule()
        results = rule.evaluate({"reading_grade": None})
        assert results[0].passed is True
        assert results[0].severity == "info"

    def test_rule_id(self):
        rule = ContentReadingLevelRule()
        assert rule.rule_id == "reading_level"


class TestKeywordStuffingRule:
    def test_pass_normal_density(self, content_rule_data):
        rule = KeywordStuffingRule()
        results = rule.evaluate(content_rule_data)
        assert results[0].passed is True

    def test_fail_stuffed(self):
        rule = KeywordStuffingRule()
        results = rule.evaluate({
            "keyword_density": {"seo": 0.15},
        })
        assert len(results) == 1
        assert results[0].passed is False

    def test_no_keywords(self):
        rule = KeywordStuffingRule()
        results = rule.evaluate({"keyword_density": {}})
        assert results[0].passed is True

    def test_rule_id(self):
        rule = KeywordStuffingRule()
        assert rule.rule_id == "keyword_stuffing"


class TestHeadingHierarchyRule:
    def test_pass_good_hierarchy(self, content_rule_data):
        rule = HeadingHierarchyRule()
        results = rule.evaluate(content_rule_data)
        assert results[0].passed is True

    def test_fail_no_headings(self):
        rule = HeadingHierarchyRule()
        results = rule.evaluate({"heading_hierarchy": []})
        assert results[0].passed is False

    def test_fail_skipped_level(self):
        rule = HeadingHierarchyRule()
        results = rule.evaluate({"heading_hierarchy": [1, 3]})
        assert results[0].passed is False

    def test_rule_id(self):
        rule = HeadingHierarchyRule()
        assert rule.rule_id == "heading_hierarchy"


class TestHeadingLengthRule:
    def test_pass_short_headings(self, content_rule_data):
        rule = HeadingLengthRule()
        results = rule.evaluate(content_rule_data)
        assert results[0].passed is True

    def test_fail_long_headings(self):
        rule = HeadingLengthRule()
        results = rule.evaluate({
            "headings": {"h1": ["A" * 100], "h2": ["B" * 80]},
            "heading_lengths": {"h1": 100, "h2": 80},
        })
        assert results[0].passed is False

    def test_rule_id(self):
        rule = HeadingLengthRule()
        assert rule.rule_id == "heading_length"


class TestTitleH1DuplicationRule:
    def test_pass_distinct_title_h1(self, content_rule_data):
        rule = TitleH1DuplicationRule()
        results = rule.evaluate(content_rule_data)
        assert results[0].passed is True

    def test_fail_identical(self):
        rule = TitleH1DuplicationRule()
        results = rule.evaluate({
            "title": "Same Title",
            "headings": {"h1": ["Same Title"]},
            "heading_counts": {"h1": 1},
        })
        assert results[0].passed is False

    def test_no_h1(self):
        rule = TitleH1DuplicationRule()
        results = rule.evaluate({"title": "A Title", "headings": {}, "heading_counts": {}})
        assert results[0].passed is True
        assert results[0].severity == "info"

    def test_rule_id(self):
        rule = TitleH1DuplicationRule()
        assert rule.rule_id == "title_h1_duplication"


class TestTitlePixelWidthRule:
    def test_pass_within_limit(self, content_rule_data):
        rule = TitlePixelWidthRule()
        results = rule.evaluate(content_rule_data)
        assert results[0].passed is True

    def test_fail_exceeds_limit(self):
        rule = TitlePixelWidthRule()
        results = rule.evaluate({"title": "T" * 100, "title_pixel_width": 800})
        assert results[0].passed is False

    def test_no_title(self):
        rule = TitlePixelWidthRule()
        results = rule.evaluate({"title": ""})
        assert results[0].passed is False
        assert results[0].severity == "info"

    def test_rule_id(self):
        rule = TitlePixelWidthRule()
        assert rule.rule_id == "title_pixel_width"


class TestMetaDescriptionPixelWidthRule:
    def test_pass_within_limit(self, content_rule_data):
        rule = MetaDescriptionPixelWidthRule()
        results = rule.evaluate(content_rule_data)
        assert results[0].passed is True

    def test_fail_exceeds_limit(self):
        rule = MetaDescriptionPixelWidthRule()
        results = rule.evaluate({"description": "D" * 200, "meta_description_pixel_width": 1400})
        assert results[0].passed is False

    def test_no_description(self):
        rule = MetaDescriptionPixelWidthRule()
        results = rule.evaluate({"description": ""})
        assert results[0].passed is False
        assert results[0].severity == "info"

    def test_rule_id(self):
        rule = MetaDescriptionPixelWidthRule()
        assert rule.rule_id == "meta_desc_pixel_width"


class TestBrokenHTMLStructureRule:
    def test_pass_valid_html(self, content_rule_data):
        rule = BrokenHTMLStructureRule()
        results = rule.evaluate(content_rule_data)
        assert results[0].passed is True

    def test_fail_missing_body(self):
        rule = BrokenHTMLStructureRule()
        results = rule.evaluate({"html_structure_errors": ["Missing <body> tag"], "html": ""})
        assert results[0].passed is False

    def test_rule_id(self):
        rule = BrokenHTMLStructureRule()
        assert rule.rule_id == "html_structure"


class TestMetaTagsInBodyRule:
    def test_pass_no_meta_in_body(self, content_rule_data):
        rule = MetaTagsInBodyRule()
        results = rule.evaluate(content_rule_data)
        assert results[0].passed is True

    def test_fail_meta_in_body(self):
        rule = MetaTagsInBodyRule()
        results = rule.evaluate({"meta_tags_in_body": ["<meta name=\"description\">"]})
        assert results[0].passed is False

    def test_rule_id(self):
        rule = MetaTagsInBodyRule()
        assert rule.rule_id == "meta_in_body"


class TestContentMimeTypeRule:
    def test_pass_html_content_type(self, content_rule_data):
        rule = ContentMimeTypeRule()
        results = rule.evaluate(content_rule_data)
        assert results[0].passed is True

    def test_fail_wrong_content_type(self):
        rule = ContentMimeTypeRule()
        results = rule.evaluate({"content_type": "application/json", "status_code": 200})
        assert results[0].passed is False

    def test_pass_redirect(self):
        rule = ContentMimeTypeRule()
        results = rule.evaluate({"content_type": "text/html", "status_code": 301})
        assert results[0].passed is True

    def test_rule_id(self):
        rule = ContentMimeTypeRule()
        assert rule.rule_id == "content_mime_type"


class TestContentRuleRegistry:
    def test_default_registry_loads_13(self):
        registry = default_content_registry()
        assert len(registry) == 13

    def test_content_rule_count_constant(self):
        assert CONTENT_RULE_COUNT == 13

    def test_all_content_rules_has_13(self):
        assert len(ALL_CONTENT_RULES) == 13

    def test_registry_run_all(self, content_rule_data):
        registry = default_content_registry()
        results = registry.run_all(content_rule_data)
        assert len(results) == 13
        assert all(isinstance(r, type(results[0])) for r in results)

    def test_registry_register_custom(self):
        registry = ContentRuleRegistry()
        registry.register(TextToHTMLRatioRule)
        assert len(registry) == 1

    def test_registry_run_all_is_fault_tolerant(self):
        registry = ContentRuleRegistry()

        class BrokenRule(BaseRule):
            rule_id = "test_broken_content"
            name = "Broken"

            def evaluate(self, data: dict) -> list:
                raise RuntimeError("boom")

        registry.register(BrokenRule)
        registry.register(TextToHTMLRatioRule)
        results = registry.run_all({"text_to_html_ratio": 0.5})
        assert len(results) == 2
        assert hasattr(results[0], "passed")
        assert results[0].rule_id == "test_broken_content"

    def test_all_rule_ids_are_slugs(self):
        for rule_cls in ALL_CONTENT_RULES:
            rule = rule_cls()
            assert rule.rule_id.replace("_", "").isalnum()
            assert "-" not in rule.rule_id
            assert rule.rule_id != ""
