"""Tests for HTML Validation rules."""
import pytest
from app.modules.rule_engine.category_rules.html_validation import (
    SingleTitleElementRule,
    SingleMetaDescriptionRule,
    DoctypeDeclarationRule,
    CharacterEncodingRule,
    ValidHeadElementsRule,
    NoscriptInHeadRule,
    SingleHeadElementRule,
    HtmlSizeLimitRule,
    NoPlaceholderTextRule,
)
from app.modules.rule_engine.models.rule_result import Severity


class TestSingleTitleElementRule:
    @pytest.fixture
    def rule(self):
        return SingleTitleElementRule()

    @pytest.mark.asyncio
    async def test_pass_single_title(self, rule):
        data = {
            "html": "<html><head><title>Test Page</title></head><body></body></html>",
            "basic": {"title": "Test Page"},
        }
        results = await rule.evaluate(data)
        assert len(results) == 1
        assert results[0].passed is True
        assert results[0].severity == Severity.PASSED
        assert "Exactly one" in results[0].message

    @pytest.mark.asyncio
    async def test_fail_no_title(self, rule):
        data = {
            "html": "<html><head></head><body></body></html>",
            "basic": {"title": ""},
        }
        results = await rule.evaluate(data)
        assert results[0].passed is False
        assert results[0].severity == Severity.WARNING
        assert "No <title> element" in results[0].message

    @pytest.mark.asyncio
    async def test_fail_multiple_titles(self, rule):
        data = {
            "html": "<html><head><title>First</title><title>Second</title></head><body></body></html>",
            "basic": {"title": "First"},
        }
        results = await rule.evaluate(data)
        assert results[0].passed is False
        assert results[0].severity == Severity.WARNING
        assert "Multiple" in results[0].message

    @pytest.mark.asyncio
    async def test_fail_empty_title(self, rule):
        data = {
            "html": "<html><head><title></title></head><body></body></html>",
            "basic": {"title": ""},
        }
        results = await rule.evaluate(data)
        assert results[0].passed is False
        assert "empty" in results[0].message


class TestSingleMetaDescriptionRule:
    @pytest.fixture
    def rule(self):
        return SingleMetaDescriptionRule()

    @pytest.mark.asyncio
    async def test_pass_single_meta_desc(self, rule):
        data = {
            "html": "<html><head><meta name='description' content='Test desc'></head><body></body></html>",
            "basic": {"meta_description": "Test desc"},
        }
        results = await rule.evaluate(data)
        assert results[0].passed is True
        assert results[0].severity == Severity.PASSED

    @pytest.mark.asyncio
    async def test_fail_no_meta_desc(self, rule):
        data = {
            "html": "<html><head></head><body></body></html>",
            "basic": {"meta_description": ""},
        }
        results = await rule.evaluate(data)
        assert results[0].passed is False
        assert "No meta description" in results[0].message

    @pytest.mark.asyncio
    async def test_fail_multiple_meta_desc(self, rule):
        data = {
            "html": "<html><head><meta name='description' content='First'><meta name='description' content='Second'></head><body></body></html>",
            "basic": {"meta_description": "First"},
        }
        results = await rule.evaluate(data)
        assert results[0].passed is False
        assert "Multiple" in results[0].message

    @pytest.mark.asyncio
    async def test_fail_empty_meta_desc(self, rule):
        data = {
            "html": "<html><head><meta name='description' content=''></head><body></body></html>",
            "basic": {"meta_description": ""},
        }
        results = await rule.evaluate(data)
        assert results[0].passed is False
        assert "empty" in results[0].message


class TestDoctypeDeclarationRule:
    @pytest.fixture
    def rule(self):
        return DoctypeDeclarationRule()

    @pytest.mark.asyncio
    async def test_pass_valid_doctype(self, rule):
        data = {"html": "<!DOCTYPE html><html><head></head><body></body></html>"}
        results = await rule.evaluate(data)
        assert results[0].passed is True
        assert results[0].severity == Severity.PASSED

    @pytest.mark.asyncio
    async def test_pass_doctype_case_insensitive(self, rule):
        data = {"html": "<!doctype html><html><head></head><body></body></html>"}
        results = await rule.evaluate(data)
        assert results[0].passed is True

    @pytest.mark.asyncio
    async def test_fail_no_doctype(self, rule):
        data = {"html": "<html><head></head><body></body></html>"}
        results = await rule.evaluate(data)
        assert results[0].passed is False
        assert "missing" in results[0].message

    @pytest.mark.asyncio
    async def test_fail_invalid_doctype(self, rule):
        data = {"html": "<!DOCTYPE HTML PUBLIC \"-//W3C//DTD HTML 4.01//EN\"><html><head></head><body></body></html>"}
        results = await rule.evaluate(data)
        assert results[0].passed is False
        assert "Non-HTML5" in results[0].message


class TestCharacterEncodingRule:
    @pytest.fixture
    def rule(self):
        return CharacterEncodingRule()

    @pytest.mark.asyncio
    async def test_pass_meta_charset(self, rule):
        data = {
            "html": "<html><head><meta charset='UTF-8'></head><body></body></html>",
            "http": {"headers": {}},
        }
        results = await rule.evaluate(data)
        assert results[0].passed is True
        assert "UTF-8" in results[0].message

    @pytest.mark.asyncio
    async def test_pass_http_header_charset(self, rule):
        data = {
            "html": "<html><head></head><body></body></html>",
            "http": {"headers": {"content-type": "text/html; charset=utf-8"}},
        }
        results = await rule.evaluate(data)
        assert results[0].passed is True

    @pytest.mark.asyncio
    async def test_fail_no_charset(self, rule):
        data = {
            "html": "<html><head></head><body></body></html>",
            "http": {"headers": {}},
        }
        results = await rule.evaluate(data)
        assert results[0].passed is False
        assert "not declared" in results[0].message


class TestValidHeadElementsRule:
    @pytest.fixture
    def rule(self):
        return ValidHeadElementsRule()

    @pytest.mark.asyncio
    async def test_pass_valid_elements(self, rule):
        data = {
            "head": {"title": ["Test"], "meta": [{"name": "desc"}], "link": [{"rel": "canonical"}]},
            "head_rendered": {},
        }
        results = await rule.evaluate(data)
        assert results[0].passed is True

    @pytest.mark.asyncio
    async def test_fail_invalid_div_in_head(self, rule):
        data = {
            "head": {"title": ["Test"], "div": [{"class": "invalid"}]},
            "head_rendered": {},
        }
        results = await rule.evaluate(data)
        assert results[0].passed is False
        assert "Invalid elements" in results[0].message
        assert "div" in results[0].message


class TestNoscriptInHeadRule:
    @pytest.fixture
    def rule(self):
        return NoscriptInHeadRule()

    @pytest.mark.asyncio
    async def test_pass_no_noscript(self, rule):
        data = {"head": {"title": ["Test"]}, "head_rendered": {}, "html": ""}
        results = await rule.evaluate(data)
        assert results[0].passed is True

    @pytest.mark.asyncio
    async def test_pass_valid_noscript_children(self, rule):
        data = {
            "head": {"noscript": [{"meta": [{"charset": "UTF-8"}]}]},
            "head_rendered": {},
            "html": "",
        }
        results = await rule.evaluate(data)
        assert results[0].passed is True

    @pytest.mark.asyncio
    async def test_fail_invalid_noscript_child(self, rule):
        data = {
            "head": {"noscript": [{"div": [{"class": "invalid"}]}]},
            "head_rendered": {},
            "html": "",
        }
        results = await rule.evaluate(data)
        assert results[0].passed is False
        assert "Invalid" in results[0].message


class TestSingleHeadElementRule:
    @pytest.fixture
    def rule(self):
        return SingleHeadElementRule()

    @pytest.mark.asyncio
    async def test_pass_single_head(self, rule):
        data = {"html": "<html><head></head><body></body></html>"}
        results = await rule.evaluate(data)
        assert results[0].passed is True

    @pytest.mark.asyncio
    async def test_fail_no_head(self, rule):
        data = {"html": "<html><body></body></html>"}
        results = await rule.evaluate(data)
        assert results[0].passed is False
        assert "No <head>" in results[0].message

    @pytest.mark.asyncio
    async def test_fail_multiple_heads(self, rule):
        data = {"html": "<html><head></head><head></head><body></body></html>"}
        results = await rule.evaluate(data)
        assert results[0].passed is False
        assert "Multiple" in results[0].message


class TestHtmlSizeLimitRule:
    @pytest.fixture
    def rule(self):
        return HtmlSizeLimitRule()

    @pytest.mark.asyncio
    async def test_pass_under_limit(self, rule):
        data = {"html": "x" * 500000, "http": {"content_length": 0}}  # ~500KB
        results = await rule.evaluate(data)
        assert results[0].passed is True

    @pytest.mark.asyncio
    async def test_fail_over_limit(self, rule):
        data = {"html": "x" * 2000000, "http": {"content_length": 0}}  # ~2MB
        results = await rule.evaluate(data)
        assert results[0].passed is False
        assert "exceeds limit" in results[0].message

    @pytest.mark.asyncio
    async def test_uses_http_content_length(self, rule):
        data = {"html": "x" * 100, "http": {"content_length": 2000000}}  # HTTP says 2MB
        results = await rule.evaluate(data)
        assert results[0].passed is False


class TestNoPlaceholderTextRule:
    @pytest.fixture
    def rule(self):
        return NoPlaceholderTextRule()

    @pytest.mark.asyncio
    async def test_pass_no_placeholder(self, rule):
        data = {"content": {"text": "This is real content about our products."}}
        results = await rule.evaluate(data)
        assert results[0].passed is True

    @pytest.mark.asyncio
    async def test_fail_lorem_ipsum(self, rule):
        data = {"content": {"text": "Lorem ipsum dolor sit amet"}}
        results = await rule.evaluate(data)
        assert results[0].passed is False
        assert "Lorem Ipsum" in results[0].message

    @pytest.mark.asyncio
    async def test_fail_todo(self, rule):
        data = {"content": {"text": "TODO: fix this later"}}
        results = await rule.evaluate(data)
        assert results[0].passed is False
        assert "TODO" in results[0].message

    @pytest.mark.asyncio
    async def test_fail_coming_soon(self, rule):
        data = {"content": {"text": "Coming soon - new features!"}}
        results = await rule.evaluate(data)
        assert results[0].passed is False
        assert "Coming Soon" in results[0].message


class TestHtmlValidationCategory:
    """Integration test for all HTML validation rules."""

    @pytest.mark.asyncio
    async def test_all_rules_load(self):
        from app.modules.scorer.services.scorer_service import ScorerService
        service = ScorerService()
        rule_ids = [r.rule_id for r in service.rules]
        
        expected = {
            "htmlval_001", "htmlval_002", "htmlval_003", "htmlval_004",
            "htmlval_005", "htmlval_006", "htmlval_007", "htmlval_008", "htmlval_009",
        }
        assert expected.issubset(set(rule_ids))

    @pytest.mark.asyncio
    async def test_all_rules_have_html_validation_category(self):
        from app.modules.scorer.services.scorer_service import ScorerService
        service = ScorerService()
        html_val_rules = [r for r in service.rules if r.category == "html_validation"]
        assert len(html_val_rules) == 9

    @pytest.mark.asyncio
    async def test_score_calculator_includes_category(self):
        from app.modules.scorer.services.score_calculator import ScoreCalculator
        calc = ScoreCalculator()
        assert "html_validation" in calc.DEFAULT_WEIGHTS
        assert calc.DEFAULT_WEIGHTS["html_validation"] == 0.02
        assert calc.CATEGORY_MAP.get("html_validation") == "html_validation"