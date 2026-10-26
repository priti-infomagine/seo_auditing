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


def _parse(items, target=TARGET, depth=10, limit=10, deep_tracking=False):
    return parse_serp_response(
        make_serp_body(items), target, depth, limit, deep_tracking=deep_tracking
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
        assert result["matches"][0]["domain"] == "example.com"
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


class TestParseStatus:
    def test_status_found(self):
        items = [
            organic_item(1, "https://other.com/page"),
            organic_item(2, "https://example.com/page"),
        ]
        result = _parse(items)
        assert result["status"] == "found"

    def test_status_not_found_in_top_10(self):
        items = [
            organic_item(1, "https://other.com/page"),
            organic_item(2, "https://another.com/"),
        ]
        result = _parse(items, deep_tracking=False)
        assert result["status"] == "not_found_in_top_10"

    def test_status_not_found_within_limit(self):
        items = [
            organic_item(1, "https://other.com/page"),
            organic_item(2, "https://another.com/"),
        ]
        result = _parse(items, deep_tracking=True)
        assert result["status"] == "not_found_within_limit"

    def test_status_no_target_when_domain_none(self):
        items = [organic_item(1, "https://example.com/")]
        result = parse_serp_response(
            make_serp_body(items), None, 10, 10, deep_tracking=False
        )
        assert result["status"] == "no_target"
        assert result["found"] is False
        assert result["best_position"] is None
        assert len(result["top_results"]) == 1

    def test_status_no_target_no_items(self):
        result = parse_serp_response(
            make_serp_body([]), None, 10, 10, deep_tracking=False
        )
        assert result["status"] == "no_target"
        assert result["found"] is False
        assert result["top_results"] == []


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

    def test_top_result_description_field(self):
        """DataForSEO returns ``description``, not ``snippet``, on organic
        items.  The parser must read ``description`` when only that key
        is present (no ``snippet`` key)."""
        items = [
            {
                "type": "organic",
                "rank_group": 1,
                "rank_absolute": 1,
                "domain": "example.com",
                "url": "https://example.com/",
                "title": "Example",
                "description": "The example domain description",
            }
        ]
        result = _parse(items)
        top = result["top_results"][0]
        assert top["snippet"] == "The example domain description"

    def test_top_result_description_takes_precedence_over_snippet(self):
        """When both ``description`` and ``snippet`` are present,
        ``description`` (the real API field) wins."""
        items = [
            {
                "type": "organic",
                "rank_group": 1,
                "rank_absolute": 1,
                "domain": "example.com",
                "url": "https://example.com/",
                "title": "Example",
                "description": "Real API snippet",
                "snippet": "Legacy field value",
            }
        ]
        result = _parse(items)
        top = result["top_results"][0]
        assert top["snippet"] == "Real API snippet"


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


class TestParseDeepTracking:
    def test_deep_tracking_finds_position_53(self):
        """Deep tracking should correctly report best_absolute_position
        when the target is at position 53 (beyond top-10)."""
        items = []
        for i in range(1, 54):
            if i == 53:
                url = "https://example.com/deep"
            else:
                url = f"https://other-{i}.com/"
            items.append(organic_item(i, url))
        result = _parse(items, depth=100, limit=10, deep_tracking=True)
        assert result["found"] is True
        assert result["status"] == "found"
        assert result["best_position"] == 53
        assert result["best_absolute_position"] == 53
        assert result["matches"][0]["url"] == "https://example.com/deep"
        assert result["matches"][0]["domain"] == "example.com"

    def test_deep_tracking_no_match_within_limit(self):
        items = [
            organic_item(i, f"https://other-{i}.com/") for i in range(1, 101)
        ]
        result = _parse(items, depth=100, limit=10, deep_tracking=True)
        assert result["found"] is False
        assert result["status"] == "not_found_within_limit"
        assert result["best_position"] is None
        assert result["best_absolute_position"] is None

    def test_standard_not_found_says_not_found_in_top_10(self):
        items = [
            organic_item(i, f"https://other-{i}.com/") for i in range(1, 11)
        ]
        result = _parse(items, depth=10, limit=10, deep_tracking=False)
        assert result["found"] is False
        assert result["status"] == "not_found_in_top_10"

    def test_deep_tracking_match_at_position_3(self):
        """Deep tracking should also find matches in the top 10."""
        items = []
        for i in range(1, 11):
            if i == 3:
                url = "https://example.com/page"
            else:
                url = f"https://other-{i}.com/"
            items.append(organic_item(i, url))
        result = _parse(items, depth=10, limit=10, deep_tracking=True)
        assert result["found"] is True
        assert result["status"] == "found"
        assert result["best_position"] == 3
        assert result["best_absolute_position"] == 3
