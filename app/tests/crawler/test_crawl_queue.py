"""
Unit tests for crawler URL classifier and crawl queue.

Tests cover:
- URL classification (HTML, RESOURCE, API, ROBOTS, SITEMAP, EXTERNAL, INVALID, IGNORED)
- Tracking parameter stripping
- CrawlQueueService add_url() with classification
- Depth, page limit, and deduplication
- Rejected URL observability
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest

from app.modules.crawler.crawl_queue import CrawlQueueService, QueueItem
from app.modules.crawler.utils.url_classifier import (
    UrlClassification,
    classify_url,
    strip_tracking_params,
)


# ---------------------------------------------------------------------------
# URL Classifier Tests
# ---------------------------------------------------------------------------

class TestUrlClassifier:
    BASE_DOMAIN = "example.com"

    def test_html_page_url(self):
        classification, reason = classify_url("https://example.com/about", self.BASE_DOMAIN)
        assert classification == UrlClassification.HTML
        assert reason == "eligible"

    def test_html_page_with_query(self):
        classification, _ = classify_url("https://example.com/page?id=123", self.BASE_DOMAIN)
        assert classification == UrlClassification.HTML

    def test_resource_css(self):
        classification, _ = classify_url("https://example.com/style.css", self.BASE_DOMAIN)
        assert classification == UrlClassification.RESOURCE
        assert "css" in _ or "extension" in _

    def test_resource_javascript(self):
        classification, _ = classify_url("https://example.com/app.js", self.BASE_DOMAIN)
        assert classification == UrlClassification.RESOURCE

    def test_resource_image(self):
        for ext in ["jpg", "jpeg", "png", "svg", "webp", "gif", "ico"]:
            classification, _ = classify_url(f"https://example.com/img.{ext}", self.BASE_DOMAIN)
            assert classification == UrlClassification.RESOURCE, f"Failed for .{ext}"

    def test_resource_font(self):
        for ext in ["woff", "woff2", "ttf", "eot"]:
            classification, _ = classify_url(f"https://example.com/font.{ext}", self.BASE_DOMAIN)
            assert classification == UrlClassification.RESOURCE, f"Failed for .{ext}"

    def test_resource_pdf(self):
        classification, _ = classify_url("https://example.com/doc.pdf", self.BASE_DOMAIN)
        assert classification == UrlClassification.RESOURCE

    def test_api_path(self):
        classification, _ = classify_url("https://example.com/api/v1/users", self.BASE_DOMAIN)
        assert classification == UrlClassification.API
        classification, _ = classify_url("https://example.com/wp-json/wp/v2/posts", self.BASE_DOMAIN)
        assert classification == UrlClassification.API
        classification, _ = classify_url("https://example.com/graphql", self.BASE_DOMAIN)
        assert classification == UrlClassification.API

    def test_api_json_extension(self):
        classification, _ = classify_url("https://example.com/data.json", self.BASE_DOMAIN)
        assert classification == UrlClassification.API

    def test_api_xml_extension(self):
        classification, _ = classify_url("https://example.com/feed.xml", self.BASE_DOMAIN)
        assert classification == UrlClassification.API

    def test_robots_txt(self):
        classification, _ = classify_url("https://example.com/robots.txt", self.BASE_DOMAIN)
        assert classification == UrlClassification.ROBOTS

    def test_sitemap_xml(self):
        classification, _ = classify_url("https://example.com/sitemap.xml", self.BASE_DOMAIN)
        assert classification == UrlClassification.SITEMAP
        classification, _ = classify_url("https://example.com/sitemap_index.xml", self.BASE_DOMAIN)
        assert classification == UrlClassification.SITEMAP

    def test_ignored_admin_paths(self):
        for path in ["/admin", "/admin/", "/wp-admin", "/wp-admin/"]:
            classification, _ = classify_url(f"https://example.com{path}", self.BASE_DOMAIN)
            assert classification == UrlClassification.IGNORED, f"Failed for {path}"

    def test_ignored_auth_paths(self):
        for path in ["/login", "/logout", "/register", "/signup", "/account", "/profile"]:
            classification, _ = classify_url(f"https://example.com{path}", self.BASE_DOMAIN)
            assert classification == UrlClassification.IGNORED, f"Failed for {path}"

    def test_ignored_ecommerce_paths(self):
        for path in ["/cart", "/cart/", "/checkout", "/checkout/", "/payment", "/payment/"]:
            classification, _ = classify_url(f"https://example.com{path}", self.BASE_DOMAIN)
            assert classification == UrlClassification.IGNORED, f"Failed for {path}"

    def test_external_domain(self):
        classification, _ = classify_url("https://external.com/page", self.BASE_DOMAIN)
        assert classification == UrlClassification.EXTERNAL
        assert "external" in _

    def test_external_domain_no_base(self):
        classification, _ = classify_url("https://external.com/page", "")
        assert classification == UrlClassification.HTML  # no base = no external check

    def test_invalid_mailto(self):
        classification, _ = classify_url("mailto:test@example.com", self.BASE_DOMAIN)
        assert classification == UrlClassification.INVALID

    def test_invalid_tel(self):
        classification, _ = classify_url("tel:+1234567890", self.BASE_DOMAIN)
        assert classification == UrlClassification.INVALID

    def test_invalid_javascript(self):
        classification, _ = classify_url("javascript:void(0)", self.BASE_DOMAIN)
        assert classification == UrlClassification.INVALID

    def test_invalid_data_uri(self):
        classification, _ = classify_url("data:text/html,<h1>hi</h1>", self.BASE_DOMAIN)
        assert classification == UrlClassification.INVALID

    def test_fragment_only(self):
        classification, _ = classify_url("#section", self.BASE_DOMAIN)
        assert classification == UrlClassification.FRAGMENT

    def test_empty_url(self):
        classification, _ = classify_url("", self.BASE_DOMAIN)
        assert classification == UrlClassification.INVALID

    def test_url_with_tracking_params(self):
        url = "https://example.com/page?utm_source=google&id=123&utm_campaign=summer"
        classification, _ = classify_url(url, self.BASE_DOMAIN)
        assert classification == UrlClassification.HTML

    def test_faceted_url_with_multiple_filter_params(self):
        url = "https://example.com/products?sort=price&filter=color:red"
        classification, _ = classify_url(url, self.BASE_DOMAIN)
        assert classification == UrlClassification.IGNORED
        assert "faceted" in _

    def test_single_query_param_not_faceted(self):
        url = "https://example.com/products?sort=price"
        classification, _ = classify_url(url, self.BASE_DOMAIN)
        assert classification == UrlClassification.HTML


class TestStripTrackingParams:
    def test_strips_utm_params(self):
        url = "https://example.com/page?utm_source=google&id=1"
        result = strip_tracking_params(url)
        assert "utm_source" not in result
        assert "id=1" in result

    def test_strips_multiple_tracking_params(self):
        url = "https://example.com/p?utm_source=g&utm_medium=cpc&utm_campaign=summer&keep=1"
        result = strip_tracking_params(url)
        assert "utm_source" not in result
        assert "utm_medium" not in result
        assert "utm_campaign" not in result
        assert "keep=1" in result

    def test_no_query_string(self):
        url = "https://example.com/page"
        result = strip_tracking_params(url)
        assert result == url

    def test_empty_query_string(self):
        url = "https://example.com/page?"
        result = strip_tracking_params(url)
        assert result == "https://example.com/page?"

    def test_preserves_regular_params(self):
        url = "https://example.com/search?q=seo&page=2"
        result = strip_tracking_params(url)
        assert "q=seo" in result
        assert "page=2" in result


# ---------------------------------------------------------------------------
# CrawlQueueService Tests
# ---------------------------------------------------------------------------

class TestCrawlQueueService:
    def test_add_url_returns_true_for_html(self):
        queue = CrawlQueueService(base_domain="example.com")
        result = queue.add_url("https://example.com/page", depth=0)
        assert result is True

    def test_add_url_rejects_resource(self):
        queue = CrawlQueueService(base_domain="example.com")
        result = queue.add_url("https://example.com/style.css", depth=0)
        assert result is False

    def test_add_url_rejects_ignored_path(self):
        queue = CrawlQueueService(base_domain="example.com")
        assert queue.add_url("https://example.com/admin/", depth=0) is False
        assert queue.add_url("https://example.com/login", depth=0) is False
        assert queue.add_url("https://example.com/cart/checkout", depth=0) is False

    def test_add_url_rejects_api(self):
        queue = CrawlQueueService(base_domain="example.com")
        assert queue.add_url("https://example.com/api/users", depth=0) is False
        assert queue.add_url("https://example.com/wp-json/wp/v2/posts", depth=0) is False

    def test_add_url_rejects_external(self):
        queue = CrawlQueueService(base_domain="example.com")
        assert queue.add_url("https://external.com/page", depth=0) is False

    def test_add_url_rejects_invalid_scheme(self):
        queue = CrawlQueueService(base_domain="example.com")
        assert queue.add_url("mailto:test@example.com", depth=0) is False
        assert queue.add_url("javascript:void(0)", depth=0) is False

    def test_add_url_rejects_duplicate(self):
        queue = CrawlQueueService(base_domain="example.com")
        assert queue.add_url("https://example.com/page", depth=0) is True
        assert queue.add_url("https://example.com/page", depth=0) is False

    def test_add_url_enqueues_and_marks_visited(self):
        queue = CrawlQueueService(base_domain="example.com")
        result = queue.add_url("https://example.com/page1", depth=0)
        assert result is True
        assert queue.remaining == 1
        assert "https://example.com/page1" in queue.visited

    def test_add_url_respects_depth_limit(self):
        queue = CrawlQueueService(max_depth=2, base_domain="example.com")
        assert queue.add_url("https://example.com/page", depth=0) is True
        assert queue.add_url("https://example.com/page", depth=1) is True
        assert queue.add_url("https://example.com/page", depth=2) is True
        assert queue.add_url("https://example.com/page", depth=3) is False

    def test_add_url_respects_page_limit(self):
        queue = CrawlQueueService(max_pages=2, base_domain="example.com")
        assert queue.add_url("https://example.com/p1", depth=0) is True
        assert queue.add_url("https://example.com/p2", depth=0) is True
        assert queue.add_url("https://example.com/p3", depth=0) is False

    def test_get_next_basic(self):
        queue = CrawlQueueService(base_domain="example.com")
        queue.add_url("https://example.com/p1", depth=0)
        queue.add_url("https://example.com/p2", depth=0)
        item = queue.get_next()
        assert item is not None
        assert item.url == "https://example.com/p1"
        assert item.depth == 0
        assert queue.remaining == 1

    def test_get_next_empty(self):
        queue = CrawlQueueService(base_domain="example.com")
        item = queue.get_next()
        assert item is None

    def test_rejected_list_tracks_reasons(self):
        queue = CrawlQueueService(base_domain="example.com")
        queue.add_url("https://example.com/style.css", depth=0)
        queue.add_url("https://example.com/admin/", depth=0)
        queue.add_url("https://external.com/", depth=0)

        assert len(queue.rejected) == 3
        classifications = [r["classification"] for r in queue.rejected]
        assert "RESOURCE" in classifications
        assert "IGNORED" in classifications
        assert "EXTERNAL" in classifications

    def test_no_base_domain_allows_external(self):
        queue = CrawlQueueService()
        result = queue.add_url("https://external.com/page", depth=0)
        assert result is True  # no base_domain = no external check

    def test_add_url_with_parent(self):
        queue = CrawlQueueService(base_domain="example.com")
        from uuid import uuid4
        parent_id = uuid4()
        result = queue.add_url("https://example.com/page", depth=1, parent_page_id=parent_id)
        assert result is True
        item = queue.get_next()
        assert item.parent_page_id == parent_id

    def test_is_empty_property(self):
        queue = CrawlQueueService(base_domain="example.com")
        assert queue.is_empty is True
        queue.add_url("https://example.com/page", depth=0)
        assert queue.is_empty is False

    def test_mark_visited(self):
        queue = CrawlQueueService(base_domain="example.com")
        queue.mark_visited("https://example.com/page")
        assert queue.add_url("https://example.com/page", depth=0) is False
