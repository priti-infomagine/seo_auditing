"""
Integration tests for CrawlScheduler URL ignore pattern integration.

Verifies that URLs matching global ignore patterns are rejected during
seed submission and discovered URL submission.
"""
import pytest
from unittest.mock import MagicMock
from types import SimpleNamespace

from app.modules.crawler.services.crawl_scheduler import CrawlScheduler
from app.modules.crawler.config import CrawlConfig
from app.modules.crawler.services.url_ignore_service import UrlIgnoreService
from uuid import uuid4


def make_pattern(scope="global", match_type=None, pattern=None, reason="test_skip"):
    return SimpleNamespace(
        scope=scope,
        match_type=match_type,
        pattern=pattern,
        reason=reason,
        description=None,
        is_active=True,
        sort_order=0,
        id=None,
        record_type="pattern",
    )


class TestCrawlSchedulerIgnoreIntegration:
    """Test that CrawlScheduler skips URLs matching global ignore patterns."""

    def test_submit_seed_ignores_matching_url(self):
        svc = UrlIgnoreService()
        svc._pattern_cache["global"] = [
            make_pattern(scope="global", match_type="path", pattern="/admin")
        ]

        mock_dedup = MagicMock()
        mock_dedup.is_url_visited = MagicMock(return_value=False)
        mock_dedup.mark_url_visited = MagicMock()

        scheduler = CrawlScheduler(
            config=CrawlConfig(),
            worker_func=MagicMock(),
            base_domain="example.com",
            ignore_service=svc,
            audit_id=uuid4(),
        )
        scheduler.dedup = mock_dedup

        result = scheduler.submit_seed("https://example.com/admin")
        assert result is False
        assert scheduler.pages_skipped_count == 1
        assert len(scheduler.skipped_urls) == 1
        assert scheduler.skipped_urls[0][2] == "test_skip"

    def test_submit_seed_allows_non_matching_url(self):
        svc = UrlIgnoreService()
        svc._pattern_cache["global"] = [
            make_pattern(scope="global", match_type="path", pattern="/admin")
        ]

        mock_dedup = MagicMock()
        mock_dedup.is_url_visited = MagicMock(return_value=False)
        mock_dedup.mark_url_visited = MagicMock()

        scheduler = CrawlScheduler(
            config=CrawlConfig(),
            worker_func=MagicMock(),
            base_domain="example.com",
            ignore_service=svc,
            audit_id=uuid4(),
        )
        scheduler.dedup = mock_dedup

        result = scheduler.submit_seed("https://example.com/home")
        assert result is True
        assert scheduler.pages_skipped_count == 0

    def test_submit_discovered_url_ignores_matching_url(self):
        svc = UrlIgnoreService()
        svc._pattern_cache["global"] = [
            make_pattern(scope="global", match_type="prefix", pattern="/api/")
        ]

        mock_dedup = MagicMock()
        mock_dedup.is_url_visited = MagicMock(return_value=False)
        mock_dedup.mark_url_visited = MagicMock()

        scheduler = CrawlScheduler(
            config=CrawlConfig(),
            worker_func=MagicMock(),
            base_domain="example.com",
            ignore_service=svc,
            audit_id=uuid4(),
        )
        scheduler.dedup = mock_dedup

        result = scheduler.submit_discovered_url(
            "https://example.com/api/v1/data",
            "https://example.com/home",
            "link",
            1,
        )
        assert result is False
        assert scheduler.pages_skipped_count == 1
        assert scheduler.skipped_urls[0][0] == "https://example.com/api/v1/data"

    def test_submit_seed_without_ignore_service(self):
        mock_dedup = MagicMock()
        mock_dedup.is_url_visited = MagicMock(return_value=False)
        mock_dedup.mark_url_visited = MagicMock()

        scheduler = CrawlScheduler(
            config=CrawlConfig(),
            worker_func=MagicMock(),
            base_domain="example.com",
            ignore_service=None,
            audit_id=None,
        )
        scheduler.dedup = mock_dedup

        result = scheduler.submit_seed("https://example.com/admin")
        assert result is True
