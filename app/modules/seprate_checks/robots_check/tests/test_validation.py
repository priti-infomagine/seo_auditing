"""
Tests for the robots.txt domain validation.
"""
import pytest

from app.modules.seprate_checks.robots_check.validation import (
    RobotsCheckValidationError,
    validate_domain,
)


def test_validate_domain_bare():
    assert validate_domain("example.com") == "example.com"


def test_validate_domain_www_stripped():
    assert validate_domain("www.example.com") == "example.com"


def test_validate_domain_uppercase():
    assert validate_domain("EXAMPLE.COM") == "example.com"


def test_validate_domain_with_port():
    assert validate_domain("example.com:8080") == "example.com"


def test_validate_domain_full_url():
    assert validate_domain("https://example.com/path") == "example.com"


def test_validate_domain_http_url():
    assert validate_domain("http://vivo.com/robots.txt") == "vivo.com"


def test_validate_domain_https_scheme_only_url():
    assert validate_domain("https://vivo.com") == "vivo.com"


def test_validate_domain_multi_level_tld():
    assert validate_domain("example.co.uk") == "example.co.uk"


def test_validate_domain_localhost_allowed():
    assert validate_domain("localhost") == "localhost"


def test_validate_domain_empty():
    with pytest.raises(RobotsCheckValidationError):
        validate_domain("")


def test_validate_domain_whitespace():
    with pytest.raises(RobotsCheckValidationError):
        validate_domain("   ")


def test_validate_domain_none():
    with pytest.raises(RobotsCheckValidationError):
        validate_domain(None)


def test_validate_domain_scheme_like_rejected():
    """A single-label string like 'htts' must be rejected, not treated as a domain."""
    with pytest.raises(RobotsCheckValidationError):
        validate_domain("htts")


def test_validate_domain_scheme_prefixed_rejected():
    """http://htts should also be rejected after scheme stripping."""
    with pytest.raises(RobotsCheckValidationError):
        validate_domain("http://htts")


def test_validate_domain_scheme_name_rejected():
    """The literal string 'https' must be rejected."""
    with pytest.raises(RobotsCheckValidationError):
        validate_domain("https")


def test_validate_domain_single_label_rejected():
    """Any single-label host without a dot must be rejected."""
    with pytest.raises(RobotsCheckValidationError):
        validate_domain("example")


@pytest.mark.parametrize(
    "bad_domain",
    ["ftp", "ws", "wss", "ftps", "sftp"],
)
def test_validate_domain_scheme_names_rejected(bad_domain):
    with pytest.raises(RobotsCheckValidationError):
        validate_domain(bad_domain)
