"""
Unit tests for host normalization (normalize_host / is_same_site) and
same-site URL classification via the URL classifier.
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest

from app.modules.crawler.utils.url_classifier import (
    UrlClassification,
    classify_url,
)
from app.shared.utils.url_utils import is_same_site, normalize_host


class TestNormalizeHost:
    def test_apex_host(self):
        assert normalize_host("example.com") == "example.com"

    def test_www_stripped(self):
        assert normalize_host("www.example.com") == "example.com"

    def test_already_lowercased(self):
        assert normalize_host("WWW.Example.COM") == "example.com"

    def test_trailing_dot_stripped(self):
        assert normalize_host("example.com.") == "example.com"

    def test_port_stripped(self):
        assert normalize_host("example.com:8080") == "example.com"

    def test_port_with_www(self):
        assert normalize_host("www.example.com:8080") == "example.com"

    def test_empty(self):
        assert normalize_host("") == ""

    def test_none_like(self):
        assert normalize_host("") == ""


class TestIsSameSite:
    # Apex ↔ www
    def test_apex_equals_www(self):
        assert is_same_site("example.com", "www.example.com") is True

    def test_www_equals_apex(self):
        assert is_same_site("www.example.com", "example.com") is True

    def test_apex_equals_apex(self):
        assert is_same_site("example.com", "example.com") is True

    # Arbitrary subdomains are NOT equivalent
    def test_subdomain_not_same(self):
        assert is_same_site("example.com", "blog.example.com") is False

    def test_shop_subdomain_not_same(self):
        assert is_same_site("example.com", "shop.example.com") is False

    def test_api_subdomain_not_same(self):
        assert is_same_site("example.com", "api.example.com") is False

    def test_www_vs_subdomain_not_same(self):
        assert is_same_site("www.example.com", "blog.example.com") is False

    # Different domains
    def test_different_domains(self):
        assert is_same_site("example.com", "example.org") is False

    def test_completely_different(self):
        assert is_same_site("foo.com", "bar.com") is False

    # Case / port variations
    def test_case_insensitive(self):
        assert is_same_site("EXAMPLE.COM", "www.Example.com") is True

    def test_port_variants_same_site(self):
        assert is_same_site("example.com:8080", "www.example.com:443") is True


class TestClassifyUrlSameSite:
    """classify_url must use same-site comparison, not exact netloc."""

    def test_www_to_apex_is_html(self):
        classification, reason = classify_url(
            "https://www.example.com/page", base_domain="example.com"
        )
        assert classification == UrlClassification.HTML

    def test_apex_to_www_is_html(self):
        classification, reason = classify_url(
            "https://example.com/page", base_domain="www.example.com"
        )
        assert classification == UrlClassification.HTML

    def test_subdomain_is_external(self):
        classification, reason = classify_url(
            "https://blog.example.com/post", base_domain="example.com"
        )
        assert classification == UrlClassification.EXTERNAL

    def test_completely_different_domain_is_external(self):
        classification, reason = classify_url(
            "https://external.com/page", base_domain="example.com"
        )
        assert classification == UrlClassification.EXTERNAL

    def test_http_https_same_site(self):
        classification, _ = classify_url(
            "http://www.example.com/page", base_domain="example.com"
        )
        assert classification == UrlClassification.HTML

    def test_api_subdomain_is_external(self):
        classification, _ = classify_url(
            "https://api.example.com/v1/users", base_domain="example.com"
        )
        assert classification == UrlClassification.EXTERNAL
