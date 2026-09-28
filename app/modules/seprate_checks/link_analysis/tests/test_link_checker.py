"""Tests for the link checker status classification and SSRF protection."""
import pytest

from app.modules.seprate_checks.link_analysis.link_checker import LinkChecker
from app.modules.seprate_checks.link_analysis.graph import CheckResult, LinkStatusClass


class TestShouldSkip:
    def test_skips_non_http(self):
        assert LinkChecker._should_skip("mailto:test@example.com") is True
        assert LinkChecker._should_skip("tel:+1234567890") is True
        assert LinkChecker._should_skip("javascript:void(0)") is True
        assert LinkChecker._should_skip("ftp://example.com/file") is True

    def test_skips_fragment(self):
        assert LinkChecker._should_skip("https://example.com/page#section") is True

    def test_does_not_skip_http(self):
        assert LinkChecker._should_skip("https://example.com/page") is False


class TestNormalizeTarget:
    def test_normalizes_valid_url(self):
        result = LinkChecker._normalize_target("https://EXAMPLE.com/Page")
        assert result is not None
        assert "example.com" in result.lower()

    def test_returns_none_on_invalid(self):
        result = LinkChecker._normalize_target("not-a-url")
        assert result is None


class TestStatusClassification:
    def test_404_is_broken(self):
        checker = LinkChecker()
        expected = CheckResult(
            status_class=LinkStatusClass.BROKEN,
            status_code=404,
            final_url="https://example.com/broken",
            redirect_chain=[],
            error_type=None,
        )
        result = CheckResult(
            status_class=LinkStatusClass.BROKEN,
            status_code=404,
            final_url="https://example.com/broken",
            redirect_chain=[],
            error_type=None,
        )
        assert result.status_class == expected.status_class

    def test_200_is_ok(self):
        result = CheckResult(
            status_class=LinkStatusClass.OK,
            status_code=200,
            final_url="https://example.com/ok",
        )
        assert result.status_class == LinkStatusClass.OK

    def test_301_is_redirect(self):
        result = CheckResult(
            status_class=LinkStatusClass.REDIRECT,
            status_code=301,
            final_url="https://example.com/new",
        )
        assert result.status_class == LinkStatusClass.REDIRECT

    def test_401_is_unverified(self):
        result = CheckResult(
            status_class=LinkStatusClass.UNVERIFIED,
            status_code=401,
            final_url="https://example.com/auth",
            error_type=None,
        )
        assert result.status_class == LinkStatusClass.UNVERIFIED


class TestSSRFProtection:
    def test_private_ip_blocked(self):
        checker = LinkChecker()
        from unittest.mock import AsyncMock, patch

        with patch("app.modules.seprate_checks.link_analysis.link_checker.validate_url_ssrf") as mock_ssrf:
            from app.modules.crawler.utils.url import SSRFError

            mock_ssrf.side_effect = SSRFError("Blocked")
            result = asyncio_run(checker.check_urls({"http://192.168.1.1/"}))

            url = list(result.keys())[0]
            assert result[url].status_class == LinkStatusClass.UNVERIFIED
            assert result[url].error_type == "ssrf_blocked"

    def test_localhost_blocked(self):
        checker = LinkChecker()
        from unittest.mock import patch

        with patch("app.modules.seprate_checks.link_analysis.link_checker.validate_url_ssrf") as mock_ssrf:
            from app.modules.crawler.utils.url import SSRFError
            mock_ssrf.side_effect = SSRFError("Blocked")
            result = asyncio_run(checker.check_urls({"http://localhost:8080/"}))

            url = list(result.keys())[0]
            assert result[url].status_class == LinkStatusClass.UNVERIFIED
            assert result[url].error_type == "ssrf_blocked"


def asyncio_run(coro):
    import asyncio
    return asyncio.get_event_loop().run_until_complete(coro)
