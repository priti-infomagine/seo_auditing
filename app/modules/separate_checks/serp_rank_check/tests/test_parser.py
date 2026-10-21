"""Tests for the SERP response parser."""
from __future__ import annotations

import pytest

from app.modules.separate_checks.serp_rank_check.exceptions import (
    SerpParseError,
)
from app.modules.separate_checks.serp_rank_check.parser import (
    parse_serp_response,
)

from .conftest import feature_item, make_serp_body, organic_item

TARGET = "example.com"


def _parse(items, target=TARGET, depth=10, limit=10):
    return parse_serp_response(
        make_serp_body(items), target, depth, limit
    )


class TestParseMatch:
    def test_found_with_match(self):
        items = [
            organic_item(1, "https://other.com/page"),
            organic_item(2, "https://example.com/page"),
            organic_item(3, "https://another.com/"),
        ]
        result = _parse(items)
        assert result["found"] is True
        assert result["best_position"] == 2
        assert result["best_absolute_position"] == 2
        assert len(result["matches"]) == 1
        assert result["matches"][0]["position"] == 2
        assert result["matches"][0]["url"] == "https://example.com/page"
        assert result["matches"][0]["title"] == "Result Title"

    def test_multiple_matches_sorted_by_position(self):
        items = [
            organic_item(1, "https://example.com/first"),
            organic_item(2, "https://other.com/"),
            organic_item(3, "https://example.com/third"),
        ]
        result = _parse(items)
        assert len(result["matches"]) == 2
        assert [m["position"] for m in result["matches"]] == [1, 3]
        assert result["best_position"] == 1

    def test_not_found_when_absent(self):
        items = [
            organic_item(1, "https://other.com/"),
            organic_item(2, "https://another.com/"),
        ]
        result = _parse(items)
        assert result["found"] is False
        assert result["best_position"] is None
        assert result["best_absolute_position"] is None
        assert result["matches"] == []

    def test_domain_matched_by_registrable_domain_not_substring(self):
        # "notexample.com" contains "example.com" as a substring
        # but is a different registrable domain — must NOT match.
        items = [
            organic_item(1, "https://notexample.com/page"),
        ]
        result = _parse(items)
        assert result["found"] is False

    def test_www_and_path_normalized(self):
        items = [
            organic_item(1, "https://www.example.com/deep/path"),
        ]
        result = _parse(items)
        assert result["found"] is True

    def test_multi_level_tld_match(self):
        items = [
            organic_item(1, "https://blog.example.co.uk/post"),
        ]
        result = _parse(items, target="example.co.uk")
        assert result["found"] is True

    def test_multi_level_tld_no_false_match(self):
        items = [
            organic_item(1, "https://example.com/page"),
        ]
        result = _parse(items, target="example.co.uk")
        assert result["found"] is False


class TestParseFeatures:
    def test_collects_non_organic_features(self):
        items = [
            organic_item(1, "https://example.com/"),
            feature_item("people_also_ask"),
            feature_item("people_also_ask"),
            feature_item("videos"),
        ]
        result = _parse(items)
        assert result["serp_features"] == ["people_also_ask", "videos"]

    def test_no_features_when_only_organic(self):
        result = _parse([organic_item(1, "https://example.com/")])
        assert result["serp_features"] == []


class TestParseTopResults:
    def test_top_results_capped(self):
        items = [
            organic_item(i, f"https://site{i}.com/") for i in range(1, 16)
        ]
        result = _parse(items, limit=10)
        assert len(result["top_results"]) == 10
        assert result["top_results"][0]["position"] == 1
        assert result["top_results"][0]["domain"] == "site1.com"
        assert result["top_results"][0]["url"] == "https://site1.com/"

    def test_top_result_fields(self):
        items = [
            organic_item(
                1,
                "https://example.com/",
                title="Example",
                snippet="The example domain",
            )
        ]
        result = _parse(items)
        top = result["top_results"][0]
        assert top == {
            "position": 1,
            "domain": "example.com",
            "url": "https://example.com/",
            "title": "Example",
            "snippet": "The example domain",
        }


class TestParsePartial:
    def test_partial_when_fewer_items_than_depth(self):
        result = _parse([organic_item(1, "https://example.com/")], depth=10)
        assert result["partial"] is True

    def test_not_partial_when_full_depth(self):
        items = [
            organic_item(i, f"https://site{i}.com/") for i in range(1, 11)
        ]
        result = _parse(items, depth=10)
        assert result["partial"] is False


class TestParseErrors:
    def test_rejects_non_object_body(self):
        with pytest.raises(SerpParseError):
            parse_serp_response([], TARGET, 10, 10)

    def test_rejects_missing_tasks(self):
        with pytest.raises(SerpParseError):
            parse_serp_response({"status_code": 20000}, TARGET, 10, 10)

    def test_rejects_missing_result(self):
        body = {"status_code": 20000, "tasks": [{"status_code": 20000}]}
        with pytest.raises(SerpParseError):
            parse_serp_response(body, TARGET, 10, 10)

    def test_rejects_invalid_target_domain(self):
        with pytest.raises(SerpParseError):
            parse_serp_response(
                make_serp_body([organic_item(1, "https://example.com/")]),
                "localhost",
                10,
                10,
            )

    def test_empty_items_is_valid_not_found(self):
        result = _parse([])
        assert result["found"] is False
        assert result["top_results"] == []
