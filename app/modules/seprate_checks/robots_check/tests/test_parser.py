"""
Tests for the robots.txt parser.
"""
import pytest

from app.modules.seprate_checks.robots_check.parser import parse_robots_txt
from app.modules.seprate_checks.robots_check.tests.conftest import load_fixture


@pytest.mark.asyncio
async def test_parser_clean():
    """Parses user-agent groups, sitemaps, and rules correctly."""
    raw = load_fixture("clean_robots.txt")
    result = parse_robots_txt(raw)

    assert len(result.user_agent_groups) == 1
    group = result.user_agent_groups[0]
    assert "*" in group["user_agents"]
    assert "/private/" in group["disallow"]
    assert len(result.sitemaps) == 1
    assert result.sitemaps[0] == "https://example.com/sitemap.xml"
    assert result.syntax_warnings == []


@pytest.mark.asyncio
async def test_parser_blank_disallow():
    """Blank Disallow directive → syntax warning, not an error."""
    raw = load_fixture("blank_disallow_robots.txt")
    result = parse_robots_txt(raw)

    assert any("Blank Disallow" in w for w in result.syntax_warnings)
    assert result.user_agent_groups is not None


@pytest.mark.asyncio
async def test_parser_site_wide_block():
    """Disallow: / → site-wide block in disallow paths."""
    raw = load_fixture("site_wide_block_robots.txt")
    result = parse_robots_txt(raw)

    assert "/" in result.user_agent_groups[0]["disallow"]


@pytest.mark.asyncio
async def test_parser_malformed():
    """Garbage lines → graceful degradation, no crash."""
    raw = load_fixture("malformed_robots.txt")
    result = parse_robots_txt(raw)

    assert "User-agent" in raw
    assert result.raw_text == raw
    assert len(result.user_agent_groups) == 1
    assert "/" not in result.user_agent_groups[0]["disallow"]
    assert "/private" in result.user_agent_groups[0]["disallow"]
    assert any("invalid" in w.lower() for w in result.syntax_warnings)


@pytest.mark.asyncio
async def test_parser_multi_ua():
    """Multiple user-agent groups parsed separately."""
    raw = load_fixture("multi_ua_robots.txt")
    result = parse_robots_txt(raw)

    uas = [g["user_agents"][0] for g in result.user_agent_groups]
    assert "googlebot" in uas
    assert "bingbot" in uas
    assert "*" in uas

    assert "/private/" in result.user_agent_groups[0]["disallow"]
    assert "/public/" in result.user_agent_groups[0]["allow"]

    assert len(result.sitemaps) == 2
    assert "https://example.com/sitemap.xml" in result.sitemaps
    assert "https://example.com/sitemap2.xml" in result.sitemaps


@pytest.mark.asyncio
async def test_parser_empty_input():
    """Empty text → empty parsed result, no crash."""
    result = parse_robots_txt("")

    assert result.user_agent_groups == []
    assert result.sitemaps == []
    assert result.syntax_warnings == []


@pytest.mark.asyncio
async def test_parser_whitespace_only():
    """Whitespace-only input → empty result."""
    result = parse_robots_txt("   \n\n  ")

    assert result.user_agent_groups == []
    assert result.sitemaps == []
