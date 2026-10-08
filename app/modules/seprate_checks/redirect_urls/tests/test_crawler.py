import gzip
import socket
import httpx
import pytest

from app.modules.seprate_checks.redirect_urls.crawler import (
    CrawlError,
    PublicHostGuard,
    canonicalize_url,
    check_redirect_chain,
    discover_site_urls,
)
from app.modules.seprate_checks.redirect_urls.graph import build_redirect_graph


class AllowHostGuard:
    async def validate(self, url: str) -> None:
        assert url.startswith(("http://", "https://"))
        return None


def test_canonicalization_reuses_project_url_rules():
    assert canonicalize_url("HTTPS://Example.test:443/a#section") == (
        "https://example.test/a"
    )


@pytest.mark.asyncio
async def test_discovery_combines_sitemap_and_internal_page_links():
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(
                200,
                text="User-agent: *\nAllow: /\nSitemap: https://example.test/sitemap.xml",
            )
        if request.url.path == "/sitemap.xml":
            return httpx.Response(
                200,
                headers={"content-type": "application/xml"},
                text=(
                    "<urlset><url><loc>https://example.test/old</loc></url>"
                    "<url><loc>https://example.test/page</loc></url></urlset>"
                ),
            )
        if request.url.path == "/":
            return httpx.Response(
                200,
                headers={"content-type": "text/html"},
                text=(
                    '<a href="/about">About</a>'
                    '<a href="https://external.test/out">External</a>'
                ),
            )
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        discovery = await discover_site_urls(
            "https://example.test",
            4,
            client,
            AllowHostGuard(),
        )

    assert discovery.robots_reachable is True
    assert discovery.urls == [
        "https://example.test/",
        "https://example.test/old",
        "https://example.test/page",
        "https://example.test/about",
    ]
    assert ("https://example.test/", "https://example.test/about") in discovery.page_edges
    assert all("external.test" not in url for url in discovery.urls)
    assert discovery.depths["https://example.test/"] == 0


@pytest.mark.asyncio
async def test_discovery_depth_zero_checks_only_the_origin():
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /")
        if request.url.path == "/":
            return httpx.Response(
                200,
                headers={"content-type": "text/html"},
                text='<a href="/about">About</a>',
            )
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        discovery = await discover_site_urls(
            "https://example.test",
            10,
            client,
            AllowHostGuard(),
            max_depth=0,
        )

    assert discovery.urls == ["https://example.test/"]
    assert discovery.depths == {"https://example.test/": 0}
    assert discovery.page_edges == [("https://example.test/", "https://example.test/about")]


@pytest.mark.asyncio
async def test_robots_server_error_stops_discovery_and_is_reported():
    requested_paths: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requested_paths.append(request.url.path)
        return httpx.Response(503)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        discovery = await discover_site_urls(
            "https://example.test",
            10,
            client,
            AllowHostGuard(),
        )

    assert discovery.urls == []
    assert discovery.robots_reachable is False
    assert discovery.errors == ["robots.txt was unreachable (HTTP 503)"]
    assert requested_paths == ["/robots.txt"]


@pytest.mark.asyncio
async def test_discovery_deduplicates_normalized_links_and_excludes_external_domains():
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /")
        if request.url.path == "/":
            return httpx.Response(
                200,
                headers={"content-type": "text/html"},
                text=(
                    '<a href="/about#one">One</a>'
                    '<a href="/about#two">Two</a>'
                    '<a href="https://other-example.test/page">External</a>'
                ),
            )
        return httpx.Response(200, headers={"content-type": "text/html"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        discovery = await discover_site_urls(
            "https://example.test",
            10,
            client,
            AllowHostGuard(),
        )

    assert discovery.urls == ["https://example.test/", "https://example.test/about"]
    assert discovery.page_edges == [
        ("https://example.test/", "https://example.test/about")
    ]


@pytest.mark.asyncio
async def test_discovery_honors_max_urls_and_includes_same_site_subdomains():
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /")
        if request.url.host == "example.test" and request.url.path == "/":
            return httpx.Response(
                200,
                headers={"content-type": "text/html"},
                text=(
                    '<a href="https://blog.example.test/post">Blog</a>'
                    '<a href="/about">About</a>'
                    '<a href="/contact">Contact</a>'
                ),
            )
        return httpx.Response(200, headers={"content-type": "text/html"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        discovery = await discover_site_urls(
            "https://example.test",
            2,
            client,
            AllowHostGuard(),
        )

    assert discovery.urls == [
        "https://example.test/",
        "https://blog.example.test/post",
    ]
    assert len(discovery.urls) == 2


@pytest.mark.asyncio
async def test_gzip_sitemap_is_bounded_and_parsed():
    sitemap = gzip.compress(
        b"<urlset><url><loc>https://example.test/page</loc></url></urlset>"
    )

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(
                200,
                text="Sitemap: https://example.test/sitemap.xml.gz",
            )
        if request.url.path == "/sitemap.xml.gz":
            return httpx.Response(200, content=sitemap)
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        discovery = await discover_site_urls(
            "https://example.test",
            5,
            client,
            AllowHostGuard(),
        )

    assert "https://example.test/page" in discovery.sitemap_urls


@pytest.mark.asyncio
@pytest.mark.parametrize("redirect_status", [301, 302, 303, 307, 308])
async def test_redirect_chain_resolves_relative_location_and_records_hops(
    redirect_status: int,
):
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/old":
            return httpx.Response(
                redirect_status,
                headers={"location": "/new"},
            )
        return httpx.Response(200)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await check_redirect_chain(
            "https://example.test/old",
            "example.test",
            client,
            AllowHostGuard(),
        )

    assert result.redirect_count == 1
    assert result.hops[0].resolved == "https://example.test/new"
    assert result.hops[0].status == redirect_status
    assert result.final_status == 200
    assert result.is_internal_redirect is True


@pytest.mark.asyncio
async def test_redirect_loop_is_marked_as_error():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/loop"
        return httpx.Response(302, headers={"location": "/loop"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await check_redirect_chain(
            "https://example.test/loop",
            "example.test",
            client,
            AllowHostGuard(),
        )

    assert result.error == "Redirect loop detected"
    assert result.error_type == "redirect_loop"
    assert result.is_broken is True
    assert result.redirect_count == 1


@pytest.mark.asyncio
async def test_missing_location_is_reported_as_malformed_redirect():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await check_redirect_chain(
            "https://example.test/old",
            "example.test",
            client,
            AllowHostGuard(),
        )

    assert result.final_status == 302
    assert result.error_type == "malformed_location"
    assert result.redirect_count == 1
    assert result.is_broken is True


@pytest.mark.asyncio
async def test_redirect_hop_limit_is_independent_and_not_exceeded_silently():
    requested_paths: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requested_paths.append(request.url.path)
        return httpx.Response(
            301,
            headers={"location": "/middle" if request.url.path == "/start" else "/next"},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await check_redirect_chain(
            "https://example.test/start",
            "example.test",
            client,
            AllowHostGuard(),
            max_hops=1,
        )

    assert result.error_type == "max_hops_exceeded"
    assert result.redirect_count == 2
    assert requested_paths == ["/start", "/middle"]


@pytest.mark.asyncio
async def test_transient_http_statuses_receive_bounded_retries():
    attempts = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(503 if attempts < 3 else 200)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await check_redirect_chain(
            "https://example.test/",
            "example.test",
            client,
            AllowHostGuard(),
        )

    assert attempts == 3
    assert result.final_status == 200
    assert result.error is None


@pytest.mark.asyncio
async def test_timeout_is_classified_for_the_url_result():
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await check_redirect_chain(
            "https://example.test/",
            "example.test",
            client,
            AllowHostGuard(),
        )

    assert result.error_type == "timeout"
    assert result.final_status is None


@pytest.mark.asyncio
async def test_public_host_guard_rejects_loopback_addresses():
    with pytest.raises(CrawlError, match="not publicly routable"):
        await PublicHostGuard().validate("http://127.0.0.1/")


@pytest.mark.asyncio
async def test_public_host_guard_classifies_dns_failures(monkeypatch):
    def fail_resolution(*args, **kwargs):
        raise socket.gaierror("name does not resolve")

    monkeypatch.setattr(socket, "getaddrinfo", fail_resolution)
    with pytest.raises(CrawlError) as error:
        await PublicHostGuard().validate("https://unresolved.example/")

    assert error.value.error_type == "dns_error"


def test_graph_contains_page_and_redirect_edges():
    from app.modules.seprate_checks.redirect_urls.schema import (
        RedirectHop,
        RedirectUrlResult,
    )

    graph = build_redirect_graph(
        ["https://example.test/old"],
        [
            RedirectUrlResult(
                url="https://example.test/old",
                hops=[
                    RedirectHop(
                        url="https://example.test/old",
                        status=301,
                        resolved="https://example.test/new",
                    )
                ],
            )
        ],
        [("https://example.test/old", "https://example.test/about")],
    )

    assert {(edge.kind, edge.source, edge.target) for edge in graph.edges} == {
        ("link", "https://example.test/old", "https://example.test/about"),
        ("redirect", "https://example.test/old", "https://example.test/new"),
    }
