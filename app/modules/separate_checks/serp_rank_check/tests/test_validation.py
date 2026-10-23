"""Tests for input normalization and validation."""
from __future__ import annotations

import hashlib
import json

import pytest

from app.modules.separate_checks.serp_rank_check.validation import (
    compute_fingerprint,
    normalize_domain,
    normalize_keyword,
    validate_depth,
    validate_device,
)


class TestNormalizeKeyword:
    def test_trims_and_collapses_whitespace(self):
        assert normalize_keyword("  hello   world  ") == "hello world"

    def test_single_space(self):
        assert normalize_keyword("seo tools") == "seo tools"

    def test_rejects_empty(self):
        with pytest.raises(ValueError):
            normalize_keyword("   ")

    def test_rejects_too_long(self):
        with pytest.raises(ValueError):
            normalize_keyword("a" * 101)

    def test_accepts_100_chars(self):
        assert len(normalize_keyword("a" * 100)) == 100

    def test_rejects_non_string(self):
        with pytest.raises(ValueError):
            normalize_keyword(123)


class TestNormalizeDomain:
    def test_strips_scheme_and_www_and_path(self):
        assert (
            normalize_domain("https://www.example.com/path?q=1")
            == "example.com"
        )

    def test_bare_domain(self):
        assert normalize_domain("Example.COM") == "example.com"

    def test_multi_level_tld(self):
        assert normalize_domain("https://blog.example.com/") == "example.com"

    def test_strips_port(self):
        assert normalize_domain("example.com:8080") == "example.com"

    def test_rejects_ip_address(self):
        with pytest.raises(ValueError):
            normalize_domain("192.168.1.1")

    def test_rejects_single_label(self):
        with pytest.raises(ValueError):
            normalize_domain("localhost")

    def test_rejects_empty(self):
        with pytest.raises(ValueError):
            normalize_domain("   ")

    def test_rejects_non_string(self):
        with pytest.raises(ValueError):
            normalize_domain(None)


class TestComputeFingerprint:
    def _fp(self, **overrides):
        params = {
            "keyword": "seo tools",
            "domain": "example.com",
            "location_name": "United States",
            "language_name": "English",
            "device": "desktop",
            "depth": 10,
        }
        params.update(overrides)
        return compute_fingerprint(**params)

    def test_deterministic(self):
        assert self._fp() == self._fp()

    def test_different_keyword_changes_fingerprint(self):
        assert self._fp() != self._fp(keyword="other")

    def test_different_device_changes_fingerprint(self):
        assert self._fp() != self._fp(device="mobile")

    def test_different_depth_changes_fingerprint(self):
        assert self._fp() != self._fp(depth=20)

    def test_different_location_changes_fingerprint(self):
        assert self._fp() != self._fp(location_name="London")

    def test_different_language_changes_fingerprint(self):
        assert self._fp() != self._fp(language_name="French")

    def test_is_sha256_hex(self):
        payload = {
            "keyword": "seo tools",
            "domain": "example.com",
            "location_name": "United States",
            "language_name": "English",
            "device": "desktop",
            "depth": 10,
        }
        expected = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        assert self._fp() == expected


class TestValidateDevice:
    def test_accepts_desktop_and_mobile(self):
        assert validate_device("desktop") == "desktop"
        assert validate_device("mobile") == "mobile"

    def test_rejects_other(self):
        with pytest.raises(ValueError):
            validate_device("tablet")


class TestValidateDepth:
    def test_accepts_allowed_depths(self):
        for depth in (10, 20, 50, 100):
            assert validate_depth(depth) == depth

    def test_rejects_other(self):
        with pytest.raises(ValueError):
            validate_depth(15)
        with pytest.raises(ValueError):
            validate_depth("10")
