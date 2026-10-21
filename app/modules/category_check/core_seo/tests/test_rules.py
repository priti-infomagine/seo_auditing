"""Tests for SEO rules — all 18 checks across 4 categories."""
from __future__ import annotations

from app.modules.category_check.core_seo.rules.base import BaseRule
from app.modules.category_check.core_seo.rules.checks import (
    CanonicalAndNoindexConflictRule,
    CanonicalHeaderValidationRule,
    CanonicalLoopDetectionRule,
    CanonicalNotPointingToHomepageRule,
    CanonicalProtocolMatchRule,
    CanonicalURLPresentRule,
    CanonicalURLValidRule,
    ConflictingCanonicalURLsRule,
    FaviconPresentRule,
    H1TagPresentRule,
    MetaDescriptionLengthRule,
    MetaDescriptionPresentRule,
    NoSnippetBlockingRule,
    RobotsMetaDirectivesRule,
    SingleH1TagRule,
    TitleTagLengthRule,
    TitleTagPresentRule,
    ViewportMetaTagRule,
)
from app.modules.category_check.core_seo.rules.registry import (
    RuleRegistry,
    default_registry,
)


class TestTitleRules:
    def test_title_present_pass(self, rule_data):
        rule = TitleTagPresentRule()
        results = rule.evaluate(rule_data)
        assert len(results) == 1
        assert results[0].passed is True

    def test_title_present_fail(self):
        rule = TitleTagPresentRule()
        results = rule.evaluate({"title": "", "url": "https://example.com"})
        assert len(results) == 1
        assert results[0].passed is False

    def test_title_too_short(self):
        rule = TitleTagLengthRule()
        results = rule.evaluate({
            "title": "Bad",
            "title_length": 3,
            "url": "https://example.com",
        })
        assert any(not r.passed for r in results)

    def test_title_length_good(self, rule_data):
        rule = TitleTagLengthRule()
        results = rule.evaluate(rule_data)
        assert results[0].passed is True


class TestMetaDescriptionRules:
    def test_meta_desc_present_pass(self, rule_data):
        rule = MetaDescriptionPresentRule()
        results = rule.evaluate(rule_data)
        assert results[0].passed is True

    def test_meta_desc_present_fail(self):
        rule = MetaDescriptionPresentRule()
        results = rule.evaluate({"description": ""})
        assert results[0].passed is False

    def test_meta_desc_too_short(self):
        rule = MetaDescriptionLengthRule()
        results = rule.evaluate({
            "description": "Short",
            "description_length": 5,
        })
        assert any(not r.passed for r in results)

    def test_meta_description_length_rule_id(self):
        rule = MetaDescriptionLengthRule()
        assert rule.rule_id == "meta_description_length"


class TestHeadingRules:
    def test_h1_present(self, rule_data):
        rule = H1TagPresentRule()
        results = rule.evaluate(rule_data)
        assert results[0].passed is True

    def test_h1_present_fail(self):
        rule = H1TagPresentRule()
        results = rule.evaluate({"heading_counts": {"h1": 0}, "headings": {}})
        assert results[0].passed is False

    def test_single_h1_pass(self, rule_data):
        rule = SingleH1TagRule()
        results = rule.evaluate(rule_data)
        assert results[0].passed is True

    def test_single_h1_fail_multiple(self):
        rule = SingleH1TagRule()
        results = rule.evaluate({"heading_counts": {"h1": 3}, "headings": {"h1": ["A", "B", "C"]}})
        assert results[0].passed is False
        assert results[0].severity == "warning"

    def test_single_h1_fail_none(self):
        rule = SingleH1TagRule()
        results = rule.evaluate({"heading_counts": {"h1": 0}, "headings": {}})
        assert results[0].passed is False


class TestCanonicalRules:
    def test_canonical_present_pass(self, rule_data):
        rule = CanonicalURLPresentRule()
        results = rule.evaluate(rule_data)
        assert results[0].passed is True

    def test_canonical_present_fail(self):
        rule = CanonicalURLPresentRule()
        results = rule.evaluate({"canonical": "", "url": "https://example.com"})
        assert results[0].passed is False

    def test_canonical_valid_pass(self, rule_data):
        rule = CanonicalURLValidRule()
        results = rule.evaluate(rule_data)
        assert results[0].passed is True

    def test_canonical_valid_fail(self):
        rule = CanonicalURLValidRule()
        results = rule.evaluate({"canonical": "not-a-url"})
        assert results[0].passed is False

    def test_canonical_not_homepage_pass(self, rule_data):
        rule = CanonicalNotPointingToHomepageRule()
        results = rule.evaluate({
            "canonical": "https://example.com/sample-page",
            "url": "https://example.com/sample-page",
        })
        assert results[0].passed is True

    def test_canonical_not_homepage_fail(self):
        rule = CanonicalNotPointingToHomepageRule()
        results = rule.evaluate({
            "canonical": "https://example.com/",
            "url": "https://example.com/sample-page",
        })
        assert results[0].passed is False

    def test_canonical_protocol_match_pass(self, rule_data):
        rule = CanonicalProtocolMatchRule()
        results = rule.evaluate({
            "canonical": "https://example.com/sample-page",
            "url": "https://example.com/sample-page",
        })
        assert results[0].passed is True

    def test_canonical_protocol_mismatch_fail(self):
        rule = CanonicalProtocolMatchRule()
        results = rule.evaluate({
            "canonical": "http://example.com/sample-page",
            "url": "https://example.com/sample-page",
        })
        assert results[0].passed is False

    def test_noindex_conflict_fail(self):
        rule = CanonicalAndNoindexConflictRule()
        results = rule.evaluate({
            "canonical": "https://example.com/page",
            "url": "https://example.com/page",
            "robots_meta": "noindex, follow",
        })
        assert results[0].passed is False
        assert results[0].severity == "warning"

    def test_noindex_no_conflict_different_url(self):
        rule = CanonicalAndNoindexConflictRule()
        results = rule.evaluate({
            "canonical": "https://example.com/other",
            "url": "https://example.com/page",
            "robots_meta": "noindex",
        })
        assert results[0].passed is True

    def test_canonical_header_single_source_pass(self, rule_data):
        rule = CanonicalHeaderValidationRule()
        results = rule.evaluate({
            "canonical": "https://example.com/sample-page",
            "canonical_source_count": 1,
            "url": "https://example.com/sample-page",
        })
        assert results[0].passed is True

    def test_conflicting_canonical_fail(self):
        rule = ConflictingCanonicalURLsRule()
        results = rule.evaluate({
            "canonical": "https://example.com/page",
            "canonical_source_count": 2,
            "url": "https://example.com/page",
        })
        assert results[0].passed is False
        assert results[0].severity == "warning"

    def test_canonical_loop_detect(self):
        rule = CanonicalLoopDetectionRule()
        results = rule.evaluate({
            "canonical": "https://example.com/other-page",
            "url": "https://example.com/sample-page",
        })
        assert results[0].passed is False


class TestTechnicalRules:
    def test_viewport_pass(self, rule_data):
        rule = ViewportMetaTagRule()
        results = rule.evaluate(rule_data)
        assert results[0].passed is True

    def test_viewport_fail(self):
        rule = ViewportMetaTagRule()
        results = rule.evaluate({"viewport": ""})
        assert results[0].passed is False

    def test_favicon_pass(self, rule_data):
        rule = FaviconPresentRule()
        results = rule.evaluate({"favicon_urls": ["/favicon.ico"]})
        assert results[0].passed is True

    def test_favicon_fail(self):
        rule = FaviconPresentRule()
        results = rule.evaluate({"favicon_urls": []})
        assert results[0].passed is False

    def test_robots_directives_pass(self):
        rule = RobotsMetaDirectivesRule()
        results = rule.evaluate({"robots_meta": "index, follow"})
        assert results[0].passed is True

    def test_robots_noindex_fail(self):
        rule = RobotsMetaDirectivesRule()
        results = rule.evaluate({"robots_meta": "noindex, follow"})
        assert results[0].passed is False
        assert results[0].severity == "warning"


class TestContentRules:
    def test_no_snippet_blocking_pass(self, rule_data):
        rule = NoSnippetBlockingRule()
        results = rule.evaluate({"robots_meta": "index, follow"})
        assert results[0].passed is True

    def test_no_snippet_blocking_fail(self):
        rule = NoSnippetBlockingRule()
        results = rule.evaluate({"robots_meta": "noindex, nosnippet"})
        assert results[0].passed is False

    def test_no_snippet_blocking_does_not_flag_nosniff(self):
        """Verify 'nosniff' (HTTP header) is not confused with 'nosnippet'."""
        rule = NoSnippetBlockingRule()
        results = rule.evaluate({"robots_meta": "nosniff"})
        assert results[0].passed is True

    def test_no_snippet_blocking_max_snippet_zero(self):
        rule = NoSnippetBlockingRule()
        results = rule.evaluate({"robots_meta": "index, max-snippet:0"})
        assert results[0].passed is False


class TestRuleIds:
    """Verify all rules use slug-format rule IDs."""

    def test_all_rule_ids_are_slugs(self):
        from app.modules.category_check.core_seo.rules.registry import ALL_RULES

        for rule_cls in ALL_RULES:
            rule = rule_cls()
            assert rule.rule_id.replace("_", "").isalnum()
            assert "-" not in rule.rule_id
            assert rule.rule_id != ""


class TestRuleRegistry:
    def test_default_registry_loads_18(self):
        registry = default_registry()
        assert len(registry) == 18

    def test_registry_run_all(self, rule_data):
        registry = default_registry()
        results = registry.run_all(rule_data)
        assert len(results) == 18
        assert all(isinstance(r, type(results[0])) for r in results)

    def test_registry_get_rules_returns_all(self):
        registry = default_registry()
        rules = registry.get_rules()
        assert len(rules) == 18

    def test_registry_register_custom(self):
        registry = RuleRegistry()
        registry.register(TitleTagPresentRule)
        assert len(registry) == 1

    def test_registry_run_all_is_fault_tolerant(self):
        registry = RuleRegistry()

        class BrokenRule(BaseRule):
            rule_id = "test_broken"
            name = "Broken"

            def evaluate(self, data: dict) -> list:
                raise RuntimeError("boom")

        registry.register(BrokenRule)
        registry.register(TitleTagPresentRule)
        results = registry.run_all({"title": "Test", "url": "https://x.com"})
        assert len(results) == 2
        # The broken rule's result should be a RuleResult (not a class), not a crash
        assert hasattr(results[0], "passed")
        assert results[0].rule_id == "test_broken"
