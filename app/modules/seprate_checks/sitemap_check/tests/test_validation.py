"""
Tests for the sitemap check URL validation.
"""
import pytest

from app.modules.seprate_checks.sitemap_check.validation import (
    SitemapCheckValidationError,
    build_sitemap_url,
    validate_url,
)


def test_validate_url_bare_domain():
    assert validate_url("example.com") == "example.com"


def test_validate_url_www_stripped():
    assert validate_url("www.example.com") == "example.com"


def test_validate_url_uppercase():
    assert validate_url("EXAMPLE.COM") == "example.com"


def test_validate_url_with_port():
    assert validate_url("example.com:8080") == "example.com"


def test_validate_url_full_https_url():
    assert validate_url("https://example.com/path") == "example.com"


def test_validate_url_full_http_url():
    assert validate_url("http://vivo.com/robots.txt") == "vivo.com"


def test_validate_url_scheme_only():
    assert validate_url("https://vivo.com") == "vivo.com"


def test_validate_url_multi_level_tld():
    assert validate_url("example.co.uk") == "example.co.uk"


def test_validate_url_with_subdomain():
    # normalize_host strips only www., not arbitrary subdomains
    assert validate_url("blog.example.com") == "blog.example.com"


def test_validate_url_localhost():
    assert validate_url("localhost") == "localhost"


def test_validate_url_empty():
    with pytest.raises(SitemapCheckValidationError):
        validate_url("")


def test_validate_url_whitespace():
    with pytest.raises(SitemapCheckValidationError):
        validate_url("   ")


def test_validate_url_none():
    with pytest.raises(SitemapCheckValidationError):
        validate_url(None)


def test_validate_url_scheme_name_rejected():
    with pytest.raises(SitemapCheckValidationError):
        validate_url("https")


def test_validate_url_single_label_rejected():
    with pytest.raises(SitemapCheckValidationError):
        validate_url("example")


def test_build_sitemap_url_default_scheme():
    assert build_sitemap_url("example.com", "/sitemap.xml") == "https://example.com/sitemap.xml"


def test_build_sitemap_url_http_scheme():
    assert build_sitemap_url("example.com", "/sitemap.xml", scheme="http") == "http://example.com/sitemap.xml"
