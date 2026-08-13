"""
Tests for RobotsService multi-group wildcard rules and is_allowed().
"""
import pytest

from app.modules.crawler.services.robots_service import RobotsPolicy, RobotsService


SAMPLE_ROBOTS = """
User-agent: *
Disallow: /admin/
Disallow: /private/
Allow: /public/

User-agent: GoogleBot
Allow: /
Disallow: /nogoogle/
"""


class TestRobotsPolicy:
    def test_wildcard_group_applies_to_unknown_agents(self):
        policy = RobotsPolicy(SAMPLE_ROBOTS)
        assert policy.is_allowed("/public/page") is True
        assert policy.is_allowed("/admin/secret") is False

    def test_specific_group_overrides_wildcard(self):
        policy = RobotsPolicy(SAMPLE_ROBOTS)
        assert policy.is_allowed("/", user_agent="GoogleBot") is True
        assert policy.is_allowed("/nogoogle/", user_agent="GoogleBot") is False

    def test_empty_path_defaults_to_root(self):
        policy = RobotsPolicy(SAMPLE_ROBOTS)
        assert policy.is_allowed("", user_agent="*") is True

    def test_no_groups_allows_all(self):
        policy = RobotsPolicy("")
        assert policy.is_allowed("/anything") is True


class TestRobotsService:
    def test_is_allowed_with_policy(self):
        service = RobotsService(user_agent="*")
        policy = RobotsPolicy(SAMPLE_ROBOTS)
        assert service.is_allowed("https://example.com/public/page", policy) is True
        assert service.is_allowed("https://example.com/admin/secret", policy) is False
