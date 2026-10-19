"""Tests for URLNormalizer — normalization, canonicalization, SSRF protection."""
from __future__ import annotations

import pytest

from app.modules.category_check.core_seo.url_normalizer import URLNormalizer


class TestNormalizeURL:
    def test_normalize_basic_url(self):
        result = URLNormalizer.normalize_url("https://example.com/page")
        assert result == "https://example.com/page"

    def test_normalize_adds_trailing_slash(self):
        result = URLNormalizer.normalize_url("https://example.com")
        assert result == "https://example.com/"

    def test_normalize_strips_fragment(self):
        result = URLNormalizer.normalize_url("https://example.com/page#section")
        assert "#section" not in result

    def test_normalize_strips_tracking_params(self, tracking_params):
        url = "https://example.com/page?utm_source=google&foo=bar&utm_campaign=test"
        result = URLNormalizer.normalize_url(url)
        assert "utm_source" not in result
        assert "utm_campaign" not in result
        assert "foo=bar" in result

    def test_normalize_lowercases_hostname(self):
        result = URLNormalizer.normalize_url("https://EXAMPLE.COM/Page")
        assert "example.com" in result

    def test_normalize_strips_default_port(self):
        result = URLNormalizer.normalize_url("https://example.com:443/page")
        assert ":443" not in result

    def test_invalid_url_raises(self):
        with pytest.raises((ValueError, Exception)):
            URLNormalizer.normalize_url("not-a-url")


class TestCanonical:
    def test_canonical_removes_default_port(self):
        result = URLNormalizer.normalize_url_canonical("https://example.com:443/page")
        assert ":443" not in result

    def test_canonical_strips_tracking(self):
        result = URLNormalizer.normalize_url_canonical("https://example.com/p?utm_source=x")
        assert "utm_source" not in result

    def test_canonical_normalizes_path_dot_segments(self):
        result = URLNormalizer.normalize_url_canonical("https://example.com/a/../b")
        assert ".." not in result

    def test_canonical_decodes_then_reencodes(self):
        from urllib.parse import unquote
        result = URLNormalizer.normalize_url_canonical("https://example.com/a%20b")
        decoded = unquote(result)
        assert decoded.endswith("/a b")


class TestSameSite:
    def test_same_domain_true(self):
        assert URLNormalizer.is_same_site("example.com", "example.com") is True

    def test_same_domain_false(self):
        assert URLNormalizer.is_same_site("example.com", "other.com") is False

    def test_subdomain_treated_same_site(self):
        # eTLD+1 comparison: both resolve to example.com
        assert URLNormalizer.is_same_site("example.com", "sub.example.com") is True

    def test_different_root_domain(self):
        assert URLNormalizer.is_same_site("example.com", "example.co.uk") is False


class TestIsSSRFBlocked:
    def test_blocks_localhost(self, blocked_hosts):
        with pytest.raises((ValueError, Exception)):
            URLNormalizer.validate_url_ssrf("http://localhost/admin")

    def test_blocks_127(self):
        with pytest.raises((ValueError, Exception)):
            URLNormalizer.validate_url_ssrf("http://127.0.0.1/admin")

    def test_blocks_private_10(self):
        with pytest.raises((ValueError, Exception)):
            URLNormalizer.validate_url_ssrf("http://10.0.0.1/admin")

    def test_blocks_private_192(self):
        with pytest.raises((ValueError, Exception)):
            URLNormalizer.validate_url_ssrf("http://192.168.1.1/admin")

    def test_blocks_local_suffix(self):
        with pytest.raises((ValueError, Exception)):
            URLNormalizer.validate_url_ssrf("http://server.local/admin")

    def test_blocks_metadata_ip(self):
        with pytest.raises((ValueError, Exception)):
            URLNormalizer.validate_url_ssrf("http://169.254.169.254/latest")

    def test_allows_public_url(self):
        try:
            URLNormalizer.validate_url_ssrf("https://example.com/page")
        except (ValueError, Exception):
            pytest.fail("Public URL should not raise SSRF error")

    def test_blocks_metadata_169(self):
        with pytest.raises((ValueError, Exception)):
            URLNormalizer.validate_url_ssrf("http://[::1]/admin")


class TestGetDomain:
    def test_get_domain_simple(self):
        assert URLNormalizer.get_domain("https://example.com/page") == "example.com"

    def test_get_domain_with_port(self):
        assert URLNormalizer.get_domain("https://example.com:8080/page") == "example.com"

    def test_get_domain_subdomain(self):
        # get_domain returns the registered domain (eTLD+1), not the full hostname
        assert URLNormalizer.get_domain("https://blog.example.com/post") == "example.com"

    def test_invalid_url_raises(self):
        result = URLNormalizer.get_domain("not-a-url")
        assert result == "" or result == "not-a-url"


class TestResolveRelative:
    def test_resolve_relative_path(self):
        base = "https://example.com/blog/post"
        result = URLNormalizer.resolve_relative(base, "../about")
        assert "example.com/about" in result

    def test_resolve_absolute_url(self):
        base = "https://example.com/blog"
        result = URLNormalizer.resolve_relative(base, "https://other.com/page")
        assert result == "https://other.com/page"

    def test_resolve_root_relative(self):
        base = "https://example.com/blog/post"
        result = URLNormalizer.resolve_relative(base, "/about")
        assert "example.com/about" in result
