"""Tests for RedirectResolver — enrichment of redirect check results."""

import pytest

from app.modules.crawler.services.site_discovery_service import (
    RobotsTxtEvidence,
    SiteDiscoveryResult,
)
from app.modules.seprate_checks.bulk_status.schema import (
    RedirectHop,
    RedirectResult,
)
from app.modules.seprate_checks.redirect_check.resolver import (
    RedirectResolver,
    ResolveContext,
)


@pytest.fixture
def sample_hops():
    return [
        RedirectHop(
            url="https://example.com/old-path",
            status=301,
            status_text="Moved Permanently",
            location="/new-path",
            resolved="https://example.com/new-path",
            latency_ms=50,
        ),
        RedirectHop(
            url="https://example.com/new-path",
            status=200,
            status_text="OK",
            location=None,
            resolved=None,
            latency_ms=30,
        ),
    ]


@pytest.fixture
def sample_check_result(sample_hops):
    return RedirectResult(
        input="https://example.com/old-path",
        hops=sample_hops,
        redirects=1,
        final_url="https://example.com/new-path",
        final_status=200,
        error=None,
    )


@pytest.fixture
def resolve_context():
    return ResolveContext(
        site_discovery=SiteDiscoveryResult(
            robots=RobotsTxtEvidence(url="https://example.com/robots.txt", exists=True, content=""),
        ),
        sitemap_url_set={"https://example.com/old-path", "https://example.com/about"},
        url_to_seo={
            "https://example.com/old-path": {
                "title": "Old Page",
                "canonical": "https://example.com/new-path",
                "page_metadata": {"meta_refresh": "5;url=https://example.com/newest"},
            },
        },
        url_to_sources={
            "https://example.com/new-path": ["https://example.com/", "https://example.com/sidebar"],
        },
        robot_parser=None,
        domain="example.com",
    )


def test_resolver_extracts_hops_from_redirect_result(sample_check_result, resolve_context):
    result = RedirectResolver.resolve(
        "https://example.com/old-path",
        sample_check_result,
        resolve_context,
    )

    assert result.url == "https://example.com/old-path"
    assert len(result.hops) == 2
    assert result.hops[0].url == "https://example.com/old-path"
    assert result.hops[0].status == 301
    assert result.hops[1].url == "https://example.com/new-path"
    assert result.hops[1].status == 200


def test_resolver_extracts_final_url_and_status(sample_check_result, resolve_context):
    result = RedirectResolver.resolve(
        "https://example.com/old-path",
        sample_check_result,
        resolve_context,
    )

    assert result.final_url == "https://example.com/new-path"
    assert result.final_status == 200
    assert result.redirect_count == 1
    assert result.is_redirect is True


def test_resolver_classifies_internal_redirect(resolve_context):
    check_result = RedirectResult(
        input="https://example.com/old-path",
        hops=[],
        redirects=1,
        final_url="https://example.com/new-path",
        final_status=200,
        error=None,
    )

    result = RedirectResolver.resolve(
        "https://example.com/old-path",
        check_result,
        resolve_context,
    )

    assert result.is_redirect is True
    assert result.is_internal_redirect is True
    assert result.is_external_redirect is False


def test_resolver_classifies_external_redirect(resolve_context):
    check_result = RedirectResult(
        input="https://example.com/old-path",
        hops=[],
        redirects=1,
        final_url="https://other.com/new-path",
        final_status=200,
        error=None,
    )

    result = RedirectResolver.resolve(
        "https://example.com/old-path",
        check_result,
        resolve_context,
    )

    assert result.is_redirect is True
    assert result.is_external_redirect is True
    assert result.is_internal_redirect is False


def test_resolver_marks_broken_when_final_status_is_4xx(resolve_context):
    check_result = RedirectResult(
        input="https://example.com/broken",
        hops=[],
        redirects=0,
        final_url="https://example.com/broken",
        final_status=404,
        error=None,
    )

    result = RedirectResolver.resolve(
        "https://example.com/broken",
        check_result,
        resolve_context,
    )

    assert result.is_broken is True


def test_resolver_marks_broken_when_error_present(resolve_context):
    check_result = RedirectResult(
        input="https://example.com/broken",
        hops=[],
        redirects=0,
        final_url="https://example.com/broken",
        final_status=None,
        error="Connection failed.",
    )

    result = RedirectResolver.resolve(
        "https://example.com/broken",
        check_result,
        resolve_context,
    )

    assert result.is_broken is True


def test_resolver_extracts_canonical_and_meta_refresh(sample_check_result, resolve_context):
    result = RedirectResolver.resolve(
        "https://example.com/old-path",
        sample_check_result,
        resolve_context,
    )

    assert result.canonical == "https://example.com/new-path"
    assert result.meta_refresh == "5;url=https://example.com/newest"


def test_resolver_checks_sitemap_membership(resolve_context):
    check_result = RedirectResult(
        input="https://example.com/old-path",
        hops=[],
        redirects=0,
        final_url="https://example.com/old-path",
        final_status=200,
        error=None,
    )

    result = RedirectResolver.resolve(
        "https://example.com/old-path",
        check_result,
        resolve_context,
    )

    assert result.in_sitemap is True


def test_resolver_extracts_source_pages(resolve_context):
    check_result = RedirectResult(
        input="https://example.com/new-path",
        hops=[],
        redirects=0,
        final_url="https://example.com/new-path",
        final_status=200,
        error=None,
    )

    result = RedirectResolver.resolve(
        "https://example.com/new-path",
        check_result,
        resolve_context,
    )

    assert "https://example.com/" in result.source_pages
    assert "https://example.com/sidebar" in result.source_pages


def test_resolver_handles_no_redirects(resolve_context):
    check_result = RedirectResult(
        input="https://example.com/no-redirect",
        hops=[],
        redirects=0,
        final_url="https://example.com/no-redirect",
        final_status=200,
        error=None,
    )

    result = RedirectResolver.resolve(
        "https://example.com/no-redirect",
        check_result,
        resolve_context,
    )

    assert result.is_redirect is False
    assert result.redirect_count == 0
    assert result.is_broken is False
