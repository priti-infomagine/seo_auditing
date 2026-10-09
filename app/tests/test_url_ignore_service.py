"""
Unit tests for UrlIgnoreService matching logic.

Tests pattern matching for each match_type (path, prefix, extension, query_param,
regex, scheme, host), scope isolation, runtime condition checks, and the
all_loaded multi-scope check mode.
"""
import re
import pytest
from types import SimpleNamespace

from app.modules.crawler.services.url_ignore_service import UrlIgnoreService


def make_pattern(scope="global", match_type=None, pattern=None, reason="test_skip",
                 description=None, is_active=True):
    """Helper: create a lightweight pattern object with the attributes check_url reads."""
    return SimpleNamespace(
        scope=scope,
        match_type=match_type,
        pattern=pattern,
        reason=reason,
        description=description,
        is_active=is_active,
        sort_order=0,
        id=None,
        record_type="pattern",
    )


class TestPathMatching:
    def test_path_exact_match(self):
        svc = UrlIgnoreService(db=None)
        svc._pattern_cache["seo"] = [
            make_pattern(scope="seo", match_type="path", pattern="/login")
        ]
        matched, reason, desc = svc.check_url("https://example.com/login", "seo")
        assert matched is True
        assert reason == "test_skip"

    def test_path_no_match(self):
        svc = UrlIgnoreService(db=None)
        svc._pattern_cache["seo"] = [
            make_pattern(scope="seo", match_type="path", pattern="/login")
        ]
        matched, reason, desc = svc.check_url("https://example.com/home", "seo")
        assert matched is False

    def test_path_case_insensitive(self):
        svc = UrlIgnoreService(db=None)
        svc._pattern_cache["global"] = [
            make_pattern(scope="global", match_type="path", pattern="/Admin")
        ]
        matched, _, _ = svc.check_url("https://example.com/admin", "global")
        assert matched is True


class TestPrefixMatching:
    def test_prefix_match(self):
        svc = UrlIgnoreService(db=None)
        svc._pattern_cache["performance"] = [
            make_pattern(scope="performance", match_type="prefix", pattern="/api/")
        ]
        matched, _, _ = svc.check_url("https://example.com/api/v1/users", "performance")
        assert matched is True

    def test_prefix_no_match(self):
        svc = UrlIgnoreService(db=None)
        svc._pattern_cache["performance"] = [
            make_pattern(scope="performance", match_type="prefix", pattern="/api/")
        ]
        matched, _, _ = svc.check_url("https://example.com/web/v1/users", "performance")
        assert matched is False


class TestExtensionMatching:
    def test_extension_match(self):
        svc = UrlIgnoreService(db=None)
        svc._pattern_cache["global"] = [
            make_pattern(scope="global", match_type="extension", pattern=".pdf")
        ]
        matched, _, _ = svc.check_url("https://example.com/docs/report.pdf", "global")
        assert matched is True

    def test_extension_no_match(self):
        svc = UrlIgnoreService(db=None)
        svc._pattern_cache["global"] = [
            make_pattern(scope="global", match_type="extension", pattern=".pdf")
        ]
        matched, _, _ = svc.check_url("https://example.com/docs/report.html", "global")
        assert matched is False


class TestQueryParamMatching:
    def test_query_param_exact(self):
        svc = UrlIgnoreService(db=None)
        svc._pattern_cache["global"] = [
            make_pattern(scope="global", match_type="query_param", pattern="gclid")
        ]
        matched, _, _ = svc.check_url("https://example.com/page?gclid=123&utm_source=foo", "global")
        assert matched is True

    def test_query_param_prefix_match(self):
        svc = UrlIgnoreService(db=None)
        svc._pattern_cache["global"] = [
            make_pattern(scope="global", match_type="query_param", pattern="utm_")
        ]
        matched, _, _ = svc.check_url("https://example.com/page?utm_campaign=summer&foo=bar", "global")
        assert matched is True

    def test_query_param_no_match(self):
        svc = UrlIgnoreService(db=None)
        svc._pattern_cache["global"] = [
            make_pattern(scope="global", match_type="query_param", pattern="gclid")
        ]
        matched, _, _ = svc.check_url("https://example.com/page?ref=home&source=direct", "global")
        assert matched is False


class TestRegexMatching:
    def test_regex_match(self):
        svc = UrlIgnoreService(db=None)
        svc._pattern_cache["seo"] = [
            make_pattern(scope="seo", match_type="regex", pattern=r"/print(/\d+)?")
        ]
        matched, _, _ = svc.check_url("https://example.com/print/123", "seo")
        assert matched is True

    def test_regex_no_match(self):
        svc = UrlIgnoreService(db=None)
        svc._pattern_cache["seo"] = [
            make_pattern(scope="seo", match_type="regex", pattern=r"/print(/\d+)?")
        ]
        matched, _, _ = svc.check_url("https://example.com/home", "seo")
        assert matched is False

    def test_regex_invalid(self):
        svc = UrlIgnoreService(db=None)
        svc._pattern_cache["seo"] = [
            make_pattern(scope="seo", match_type="regex", pattern=r"[invalid(")
        ]
        matched, _, _ = svc.check_url("https://example.com/home", "seo")
        assert matched is False


class TestSchemeMatching:
    def test_scheme_match(self):
        svc = UrlIgnoreService(db=None)
        svc._pattern_cache["global"] = [
            make_pattern(scope="global", match_type="scheme", pattern="ftp")
        ]
        matched, _, _ = svc.check_url("ftp://example.com/file", "global")
        assert matched is True

    def test_scheme_no_match(self):
        svc = UrlIgnoreService(db=None)
        svc._pattern_cache["global"] = [
            make_pattern(scope="global", match_type="scheme", pattern="ftp")
        ]
        matched, _, _ = svc.check_url("https://example.com/file", "global")
        assert matched is False


class TestHostMatching:
    def test_host_match(self):
        svc = UrlIgnoreService(db=None)
        svc._pattern_cache["global"] = [
            make_pattern(scope="global", match_type="host", pattern="ads.example.com")
        ]
        matched, _, _ = svc.check_url("https://ads.example.com/banner", "global")
        assert matched is True

    def test_host_no_match(self):
        svc = UrlIgnoreService(db=None)
        svc._pattern_cache["global"] = [
            make_pattern(scope="global", match_type="host", pattern="ads.example.com")
        ]
        matched, _, _ = svc.check_url("https://blog.example.com/post", "global")
        assert matched is False


class TestScopeIsolation:
    def test_scope_isolation(self):
        svc = UrlIgnoreService(db=None)
        svc._pattern_cache["global"] = [
            make_pattern(scope="global", match_type="path", pattern="/admin")
        ]
        matched, _, _ = svc.check_url("https://example.com/admin", "seo")
        assert matched is False

    def test_unloaded_scope_returns_no_match(self):
        svc = UrlIgnoreService(db=None)
        matched, _, _ = svc.check_url("https://example.com/anything", "global")
        assert matched is False


class TestAllLoadedMode:
    def test_all_loaded_finds_match(self):
        svc = UrlIgnoreService(db=None)
        svc._pattern_cache["global"] = [
            make_pattern(scope="global", match_type="prefix", pattern="/cart")
        ]
        svc._pattern_cache["seo"] = [
            make_pattern(scope="seo", match_type="path", pattern="/login")
        ]
        matched, reason, scope = svc.check_url("https://example.com/cart/checkout", all_loaded=True)
        assert matched is True
        assert scope == "global"

    def test_all_loaded_no_match(self):
        svc = UrlIgnoreService(db=None)
        svc._pattern_cache["global"] = [
            make_pattern(scope="global", match_type="path", pattern="/admin")
        ]
        matched, _, _ = svc.check_url("https://example.com/home", all_loaded=True)
        assert matched is False

    def test_all_loaded_empty_cache(self):
        svc = UrlIgnoreService(db=None)
        matched, _, _ = svc.check_url("https://example.com/home", all_loaded=True)
        assert matched is False


class TestRuntimeConditions:
    def test_redirect_source(self):
        svc = UrlIgnoreService(db=None)
        page = SimpleNamespace(
            is_redirect=True,
            status_code=301,
            normalized_url="https://example.com/old",
            url="https://example.com/old",
            path="/old",
        )
        is_skipped, reason = svc.check_runtime_conditions(page)
        assert is_skipped is True
        assert reason == "redirect_source"

    def test_error_page(self):
        svc = UrlIgnoreService(db=None)
        page = SimpleNamespace(
            is_redirect=False,
            status_code=404,
            normalized_url="https://example.com/notfound",
            url="https://example.com/notfound",
            path="/notfound",
        )
        is_skipped, reason = svc.check_runtime_conditions(page)
        assert is_skipped is True
        assert reason == "error_page"

    def test_long_url_not_skipped(self):
        svc = UrlIgnoreService(db=None)
        long_path = "/" + "a" * 2100
        page = SimpleNamespace(
            is_redirect=False,
            status_code=200,
            normalized_url=f"https://example.com{long_path}",
            url=f"https://example.com{long_path}",
            path=long_path,
        )
        is_skipped, reason = svc.check_runtime_conditions(page)
        assert is_skipped is False
        assert reason is None


    def test_too_many_params(self):
        svc = UrlIgnoreService(db=None)
        query = "&".join([f"p{i}=v{i}" for i in range(10)])
        page = SimpleNamespace(
            is_redirect=False,
            status_code=200,
            normalized_url=f"https://example.com/page?{query}",
            url=f"https://example.com/page?{query}",
            path="/page",
        )
        is_skipped, reason = svc.check_runtime_conditions(page)
        assert is_skipped is True
        assert reason == "too_many_params"

    def test_no_runtime_skip(self):
        svc = UrlIgnoreService(db=None)
        page = SimpleNamespace(
            is_redirect=False,
            status_code=200,
            normalized_url="https://example.com/page",
            url="https://example.com/page",
            path="/page",
        )
        is_skipped, reason = svc.check_runtime_conditions(page)
        assert is_skipped is False
        assert reason is None

    def test_none_page(self):
        svc = UrlIgnoreService(db=None)
        is_skipped, reason = svc.check_runtime_conditions(None)
        assert is_skipped is False
        assert reason is None


class TestCacheManagement:
    def test_clear_cache(self):
        svc = UrlIgnoreService(db=None)
        svc._pattern_cache["global"] = [make_pattern()]
        svc._regex_cache["test"] = re.compile("test")
        assert len(svc._pattern_cache) == 1
        assert len(svc._regex_cache) == 1
        svc.clear_cache()
        assert len(svc._pattern_cache) == 0
        assert len(svc._regex_cache) == 0


class TestParamExtraction:
    def test_extract_param_names(self):
        svc = UrlIgnoreService(db=None)
        params = svc._extract_param_names("utm_source=google&gclid=123&ref=home")
        assert params == ["utm_source", "gclid", "ref"]

    def test_extract_param_names_empty(self):
        svc = UrlIgnoreService(db=None)
        params = svc._extract_param_names("")
        assert params == []

    def test_extract_param_names_no_query(self):
        svc = UrlIgnoreService(db=None)
        params = svc._extract_param_names(None)
        assert params == []


class TestCategoryEvaluations:
    def test_performance_skip_error_and_redirect(self):
        svc = UrlIgnoreService(db=None)
        redirect_page = SimpleNamespace(
            is_redirect=True,
            status_code=301,
            url="https://example.com/old",
            normalized_url="https://example.com/old",
            path="/old",
        )
        should_check, reason = svc.should_check_performance(redirect_page)
        assert should_check is False
        assert reason == "redirect_source"

    def test_performance_template_sampling(self):
        svc = UrlIgnoreService(db=None)
        counts = {}
        for i in range(7):
            page = SimpleNamespace(
                is_redirect=False,
                status_code=200,
                url=f"https://example.com/products/{i}",
                normalized_url=f"https://example.com/products/{i}",
                path=f"/products/{i}",
            )
            should_check, reason = svc.should_check_performance(page, template_cluster_counts=counts, max_sample_per_template=5)
            if i < 5:
                assert should_check is True
            else:
                assert should_check is False
                assert reason == "same_template_sample_capped"

    def test_accessibility_template_dedup(self):
        svc = UrlIgnoreService(db=None)
        seen = set()
        p1 = SimpleNamespace(
            is_redirect=False,
            status_code=200,
            url="https://example.com/blog/101",
            normalized_url="https://example.com/blog/101",
            path="/blog/101",
        )
        p2 = SimpleNamespace(
            is_redirect=False,
            status_code=200,
            url="https://example.com/blog/102",
            normalized_url="https://example.com/blog/102",
            path="/blog/102",
        )
        c1, r1 = svc.should_check_accessibility(p1, template_seen=seen)
        c2, r2 = svc.should_check_accessibility(p2, template_seen=seen)
        assert c1 is True
        assert c2 is False
        assert r2 == "same_template_duplicate"

    def test_seo_intentionally_hidden_noindex(self):
        svc = UrlIgnoreService(db=None)
        page = SimpleNamespace(
            is_redirect=False,
            status_code=200,
            url="https://example.com/lp/sale",
            normalized_url="https://example.com/lp/sale",
            path="/lp/sale",
        )
        should_check, reason, is_hidden = svc.should_check_seo(page, robots_meta="noindex, follow")
        assert should_check is True
        assert reason == "noindex_by_design"
        assert is_hidden is True

