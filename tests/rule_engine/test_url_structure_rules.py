"""
Unit tests for URL Structure category rules.
"""
import pytest
from urllib.parse import urlsplit
from app.modules.rule_engine.category_rules.url_structure import (
    ALL_URL_STRUCTURE_RULES,
    NoDoubleSlashes,
    NoInternalSearchUrls,
    NoRawNonAscii,
    NoRepetitiveSegments,
    NoSessionIds,
    NoSpacesInUrl,
    NoStopWords,
    NoTrackingParameters,
    NoUnderscores,
    NoUppercase,
    UrlLength,
    UrlParameters,
    SlugQuality,
    NoHashRouting,
    ValidUrlEncoding,
)
from app.modules.rule_engine.config.url_structure_config import UrlStructureConfig
from app.modules.rule_engine.category_rules.url_structure_utils import UrlRecord, build_records, tokens, looks_random
from app.modules.rule_engine.models.rule_result import Severity
from urllib.parse import SplitResult


def make_record(url: str, raw: str = None, scope: str = 'page') -> UrlRecord:
    """Helper to create a UrlRecord for testing."""
    from urllib.parse import urlsplit
    parts = urlsplit(url)
    return UrlRecord(
        url=url,
        raw=raw or url,
        scope=scope,
        parts=parts
    )


class TestUrlStructureUtils:
    """Tests for shared utilities."""

    def test_tokens(self):
        assert tokens("hello-world") == ["hello", "world"]
        assert tokens("hello_world") == ["hello", "world"]
        assert tokens("Hello World!") == ["hello", "world"]
        assert tokens("café-restaurant") == ["café", "restaurant"]
        assert tokens("") == []

    def test_looks_random(self):
        assert looks_random("abc123def456ghi789") is True
        assert looks_random("abcdef") is False  # no digits
        assert looks_random("123456") is False  # no letters
        assert looks_random("abc-123") is False  # too short (< 16 chars)
        assert looks_random("short") is False  # too short
        assert looks_random("abc@123") is False  # special char

    def test_build_records_deduplicates(self):
        cfg = UrlStructureConfig(max_links=500)
        data = {
            'url': {'final_url': 'https://example.com/page'},
            'links': {
                'internal_links': [
                    {'absolute_url': 'https://example.com/page', 'href': '/page'},
                    {'absolute_url': 'https://example.com/other', 'href': '/other'},
                ]
            }
        }
        records = build_records(data, cfg)
        assert len(records) == 2
        assert records[0].scope == 'page'
        assert records[1].scope == 'link'

    def test_build_records_skips_non_http(self):
        cfg = UrlStructureConfig(max_links=500)
        data = {
            'url': {'final_url': 'https://example.com/page'},
            'links': {
                'internal_links': [
                    {'absolute_url': 'mailto:test@example.com', 'href': 'mailto:test@example.com'},
                    {'absolute_url': 'javascript:void(0)', 'href': 'javascript:void(0)'},
                ]
            }
        }
        records = build_records(data, cfg)
        assert len(records) == 1  # only page URL

    def test_build_records_caps_links(self):
        cfg = UrlStructureConfig(max_links=2)
        data = {
            'url': {'final_url': 'https://example.com/page'},
            'links': {
                'internal_links': [
                    {'absolute_url': f'https://example.com/page{i}', 'href': f'/page{i}'}
                    for i in range(10)
                ]
            }
        }
        records = build_records(data, cfg)
        assert len(records) == 3  # page + 2 links
        assert records[-1].url == 'https://example.com/page1'


class TestNoDoubleSlashes:
    """Tests for url_structure_001."""

    @pytest.mark.parametrize("url,should_flag", [
        ("https://example.com/blog//article", True),
        ("https://example.com//", True),
        ("https://example.com/a?r=https://x.com", False),  # query string ignored
        ("https://example.com/", False),
        ("https://example.com/a/b/c", False),
    ])
    def test_double_slashes(self, url, should_flag):
        rule = NoDoubleSlashes()
        cfg = UrlStructureConfig()
        rec = make_record(url)
        result = rule.check(rec, cfg, {})
        if should_flag:
            assert result is not None
            assert result['path'] == urlsplit(url).path
        else:
            assert result is None


class TestNoInternalSearchUrls:
    """Tests for url_structure_002."""

    @pytest.mark.parametrize("url,should_flag", [
        ("https://example.com/search/shoes", True),
        ("https://example.com/search-results/", True),
        ("https://example.com/?s=shoes", True),
        ("https://example.com/?q=test", True),
        ("https://example.com/search-engine-optimization/", False),
        ("https://example.com/blog/search-tips", False),
    ])
    def test_search_urls(self, url, should_flag):
        rule = NoInternalSearchUrls()
        cfg = UrlStructureConfig()
        rec = make_record(url)
        result = rule.check(rec, cfg, {})
        if should_flag:
            assert result is not None
        else:
            assert result is None


class TestNoRawNonAscii:
    """Tests for url_structure_003."""

    @pytest.mark.parametrize("url,raw,should_flag", [
        ("https://example.com/caf%C3%A9", "https://example.com/café", True),  # raw has non-ASCII
        ("https://example.com/caf%C3%A9", "https://example.com/caf%C3%A9", False),  # encoded
        ("https://example.com/पुदीना", "https://example.com/पुदीना", True),  # Hindi raw
        ("https://example.com/%E0%A4%AA%E0%A5%81%E0%A4%A6%E0%A5%80%E0%A4%A8%E0%A4%BE", "https://example.com/पुदीना", True),  # encoded Hindi
    ])
    def test_non_ascii(self, url, raw, should_flag):
        rule = NoRawNonAscii()
        cfg = UrlStructureConfig()
        rec = make_record(url, raw=raw)
        result = rule.check(rec, cfg, {})
        if should_flag:
            assert result is not None
        else:
            assert result is None


class TestNoRepetitiveSegments:
    """Tests for url_structure_004."""

    @pytest.mark.parametrize("url,should_flag", [
        ("https://example.com/blog/blog/post", True),
        ("https://example.com/a/b/a/b/", True),
        ("https://example.com/2024/01/01/", False),  # numeric blocks ignored
        ("https://example.com/page/2/2", False),  # numeric blocks ignored
        ("https://example.com/a/a/", True),
        ("https://example.com/a/b/c", False),
    ])
    def test_repetitive(self, url, should_flag):
        rule = NoRepetitiveSegments()
        cfg = UrlStructureConfig()
        rec = make_record(url)
        result = rule.check(rec, cfg, {})
        if should_flag:
            assert result is not None
            assert 'segments' in result
        else:
            assert result is None


class TestNoSessionIds:
    """Tests for url_structure_005."""

    @pytest.mark.parametrize("url,should_flag,severity", [
        ("https://example.com/?PHPSESSID=abc123", True, Severity.CRITICAL),
        ("https://example.com/?jsessionid=ABC123DEF", True, Severity.CRITICAL),
        ("https://example.com/x;jsessionid=9F8E7D6C", True, Severity.CRITICAL),
        ("https://example.com/?sid=789", False, Severity.INFO),  # too short
        ("https://example.com/?token=abc", False, Severity.INFO),  # not random enough
        ("https://example.com/?sid=abc123def456ghi789", True, Severity.WARNING),  # guarded + random
    ])
    def test_session_ids(self, url, should_flag, severity):
        rule = NoSessionIds()
        cfg = UrlStructureConfig()
        rec = make_record(url)
        result = rule.check(rec, cfg, {})
        if should_flag:
            assert result is not None
            assert 'hits' in result
            # Check severity logic
            issues = [{'hits': result['hits']}]
            assert rule.result_severity(issues) == severity
        else:
            assert result is None


class TestNoSpacesInUrl:
    """Tests for url_structure_006."""

    @pytest.mark.parametrize("url,raw,should_flag", [
        ("https://example.com/my%20page", "https://example.com/my page", True),
        ("https://example.com/my%20page", "https://example.com/my%20page", True),
        ("https://example.com/?q=a%20b", "https://example.com/?q=a b", False),  # query ignored
        ("https://example.com/my-page", "https://example.com/my-page", False),
    ])
    def test_spaces(self, url, raw, should_flag):
        rule = NoSpacesInUrl()
        cfg = UrlStructureConfig()
        rec = make_record(url, raw=raw)
        result = rule.check(rec, cfg, {})
        if should_flag:
            assert result is not None
        else:
            assert result is None


class TestNoStopWords:
    """Tests for url_structure_007."""

    @pytest.mark.parametrize("url,lang,should_flag", [
        ("https://example.com/the-best-guide-to-seo", "en", True),  # 3 stop words
        ("https://example.com/state-of-the-art", "en", True),  # 2 stop words (of, the)
        ("https://example.com/guida-migliore-seo", "it", False),  # non-English
        ("https://example.com/running-shoes", "en", False),
    ])
    def test_stop_words(self, url, lang, should_flag):
        rule = NoStopWords()
        cfg = UrlStructureConfig()
        rec = make_record(url)
        data = {'basic': {'language': lang}, 'headings': {'h1': []}}
        result = rule.check(rec, cfg, data)
        if should_flag:
            assert result is not None
            assert 'stop_words_found' in result
        else:
            assert result is None


class TestNoTrackingParameters:
    """Tests for url_structure_008."""

    @pytest.mark.parametrize("url,should_flag,expected_severity", [
        ("https://example.com/?utm_source=google", True, Severity.WARNING),
        ("https://example.com/?fbclid=123", True, Severity.WARNING),
        ("https://example.com/?ref=nav", False, Severity.INFO),  # generic name excluded
        ("https://example.com/?source=blog", False, Severity.INFO),  # generic name excluded
        ("https://example.com/?hsa_cam=123", True, Severity.WARNING),
    ])
    def test_tracking_params(self, url, should_flag, expected_severity):
        rule = NoTrackingParameters()
        cfg = UrlStructureConfig()
        rec = make_record(url, scope='link')  # internal link -> WARNING
        result = rule.check(rec, cfg, {})
        if should_flag:
            assert result is not None
            assert 'params' in result
            # Create proper issue dict with scope
            issues = [{'scope': 'link', **result}]
            assert rule.result_severity(issues) == expected_severity
        else:
            assert result is None


class TestNoUnderscores:
    """Tests for url_structure_009."""

    @pytest.mark.parametrize("url,should_flag", [
        ("https://example.com/my_post", True),
        ("https://example.com/_next/static/file.js", False),  # framework path
        ("https://example.com/my-post", False),
        ("https://example.com/image.jpg", False),  # asset
    ])
    def test_underscores(self, url, should_flag):
        rule = NoUnderscores()
        cfg = UrlStructureConfig()
        rec = make_record(url)
        result = rule.check(rec, cfg, {})
        if should_flag:
            assert result is not None
        else:
            assert result is None


class TestNoUppercase:
    """Tests for url_structure_010."""

    @pytest.mark.parametrize("url,should_flag", [
        ("https://example.com/Blog/Post", True),
        ("https://example.com/caf%C3%A9", False),  # encoded uppercase in % is fine
        ("https://Example.com/blog", False),  # host ignored
        ("https://example.com/blog", False),
    ])
    def test_uppercase(self, url, should_flag):
        rule = NoUppercase()
        cfg = UrlStructureConfig()
        rec = make_record(url)
        result = rule.check(rec, cfg, {})
        if should_flag:
            assert result is not None
        else:
            assert result is None


class TestUrlLength:
    """Tests for url_structure_011."""

    @pytest.mark.parametrize("url,expected_level", [
        ("https://example.com/" + "a" * 150, "INFO"),  # path > 100
        ("https://example.com/" + "a" * 250, "INFO"),  # total > 200 but < 2000
        ("https://example.com/" + "a" * 2500, "WARNING"),  # total > 2000
        ("https://example.com/short", None),  # no flag
    ])
    def test_length(self, url, expected_level):
        rule = UrlLength()
        cfg = UrlStructureConfig()
        rec = make_record(url)
        result = rule.check(rec, cfg, {})
        if expected_level:
            assert result is not None
            assert result['level'] == expected_level
        else:
            assert result is None


class TestUrlParameters:
    """Tests for url_structure_012."""

    @pytest.mark.parametrize("url,should_flag", [
        ("https://example.com/?a=1&b=2&c=3&d=4&e=5&f=6", True),  # 6 params
        ("https://example.com/?a=1&b=2&c=3&d=4&e=5", False),  # 5 params
        ("https://example.com/", False),
    ])
    def test_params(self, url, should_flag):
        rule = UrlParameters()
        cfg = UrlStructureConfig()
        rec = make_record(url)
        result = rule.check(rec, cfg, {})
        if should_flag:
            assert result is not None
            assert result['param_count'] == 6
        else:
            assert result is None


class TestSlugQuality:
    """Tests for url_structure_013."""

    @pytest.mark.parametrize("url,should_flag,issue_type", [
        ("https://example.com/12345", True, 'numeric_id'),
        ("https://example.com/abcdef1234567890abcdef1234567890", True, 'hash_like'),
        ("https://example.com/?p=123", True, 'parameter_only'),
        ("https://example.com/running-shoes-guide", False, None),
    ])
    def test_slug_quality(self, url, should_flag, issue_type):
        rule = SlugQuality()
        cfg = UrlStructureConfig()
        rec = make_record(url, scope='page')
        data = {'basic': {'title': 'Running Shoes Guide', 'language': 'en'}, 'headings': {'h1': ['Running Shoes Guide']}}
        result = rule.check(rec, cfg, data)
        if should_flag:
            assert result is not None
            assert result['issue'] == issue_type
        else:
            assert result is None


class TestNoHashRouting:
    """Tests for url_structure_014."""

    @pytest.mark.parametrize("url,raw,should_flag", [
        ("https://example.com/#/potatoes", "https://example.com/#/potatoes", True),
        ("https://example.com/#!/about", "https://example.com/#!/about", True),
        ("https://example.com/#pricing", "https://example.com/#pricing", False),
        ("https://example.com/page#section", "https://example.com/page#section", False),
    ])
    def test_hash_routing(self, url, raw, should_flag):
        rule = NoHashRouting()
        cfg = UrlStructureConfig()
        rec = make_record(url, raw=raw)
        result = rule.check(rec, cfg, {})
        if should_flag:
            assert result is not None
        else:
            assert result is None


class TestValidUrlEncoding:
    """Tests for url_structure_015."""

    @pytest.mark.parametrize("url,raw,should_flag", [
        ("https://example.com/a%zz", "https://example.com/a%zz", True),  # invalid hex
        ("https://example.com/a%E9", "https://example.com/a%E9", True),  # invalid UTF-8
        ("https://example.com/?a,,b,,c", "https://example.com/?a,,b,,c", True),  # custom delimiters
        ("https://example.com/?amp", "https://example.com/?amp", False),  # simple flag OK
        ("https://example.com/?a=1&b=2", "https://example.com/?a=1&b=2", False),
    ])
    def test_encoding(self, url, raw, should_flag):
        rule = ValidUrlEncoding()
        cfg = UrlStructureConfig()
        rec = make_record(url, raw=raw)
        result = rule.check(rec, cfg, {})
        if should_flag:
            assert result is not None
        else:
            assert result is None


class TestAllRulesLoad:
    """Test that all 15 rules can be instantiated."""

    def test_all_rules_instantiate(self):
        for rule_cls in ALL_URL_STRUCTURE_RULES:
            rule = rule_cls()
            assert rule.rule_id.startswith('url_structure_')
            assert rule.name
            assert rule.category == 'url_structure'

    def test_rule_count(self):
        assert len(ALL_URL_STRUCTURE_RULES) == 15


if __name__ == '__main__':
    pytest.main([__file__, '-v'])