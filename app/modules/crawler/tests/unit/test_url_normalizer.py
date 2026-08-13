"""
Tests for URL normalization and SSRF protection.
"""
import pytest

from app.modules.crawler.exceptions import SSRFError
from app.modules.crawler.utils.url import (
    normalize_url_canonical,
    validate_url_ssrf,
    is_ip_private,
)


class TestNormalizeUrlCanonical:
    def test_scheme_lowercased(self):
        result = normalize_url_canonical("HTTPS://Example.com/Page")
        assert result.startswith("https://")

    def test_host_lowercased(self):
        result = normalize_url_canonical("https://EXAMPLE.COM/Page")
        assert "example.com" in result

    def test_default_port_removed_http(self):
        result = normalize_url_canonical("http://example.com:80/page")
        assert ":80" not in result

    def test_default_port_removed_https(self):
        result = normalize_url_canonical("https://example.com:443/page")
        assert ":443" not in result

    def test_non_default_port_preserved(self):
        result = normalize_url_canonical("http://example.com:8080/page")
        assert ":8080" in result

    def test_fragment_stripped(self):
        result = normalize_url_canonical("https://example.com/page#section")
        assert "#" not in result

    def test_tracking_params_removed(self):
        result = normalize_url_canonical("https://example.com/page?utm_source=google&id=1")
        assert "utm_source" not in result
        assert "id=1" in result

    def test_query_params_sorted(self):
        result = normalize_url_canonical("https://example.com/page?b=2&a=1")
        assert result.index("a=1") < result.index("b=2")

    def test_trailing_slash_preserved_by_default(self):
        result = normalize_url_canonical("https://example.com/")
        assert result.endswith("/")


class TestSSRFProtection:
    def test_localhost_blocked(self):
        with pytest.raises(SSRFError):
            validate_url_ssrf("http://127.0.0.1/test")

    def test_private_10_network_blocked(self):
        with pytest.raises(SSRFError):
            validate_url_ssrf("http://10.0.0.1/test")

    def test_private_192_168_network_blocked(self):
        with pytest.raises(SSRFError):
            validate_url_ssrf("http://192.168.1.1/test")

    def test_private_172_16_network_blocked(self):
        with pytest.raises(SSRFError):
            validate_url_ssrf("http://172.16.0.1/test")

    def test_loopback_ipv6_blocked(self):
        with pytest.raises(SSRFError):
            validate_url_ssrf("http://[::1]/test")

    def test_allow_private_ips_skips_check(self):
        validate_url_ssrf("http://127.0.0.1/test", allow_private=True)


class TestIsIpPrivate:
    def test_loopback(self):
        assert is_ip_private("127.0.0.1") is True

    def test_private_10(self):
        assert is_ip_private("10.0.0.1") is True

    def test_private_192_168(self):
        assert is_ip_private("192.168.1.1") is True

    def test_public_ip(self):
        assert is_ip_private("8.8.8.8") is False
