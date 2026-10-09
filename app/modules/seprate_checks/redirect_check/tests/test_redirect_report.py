"""Tests for redirect_report: counting, states, client-side detection, SSRF hook, slim payload."""
from __future__ import annotations

import asyncio

import httpx

from app.modules.seprate_checks.redirect_check.redirect_report import (
    BlockedURL,
    analyze_result,
    build_findings,
    build_report,
    detect_client_redirect,
    fetch_chain,
    public_result,
)

B = "https://site.com"


def hop(url, status, loc=None, **extra):
    return {"url": url, "status": status, "location": loc, "latency_ms": 5, **extra}


def raw(url, hops, error=None, error_type=None, **extra):
    return {"url": url, "hops": hops, "error": error, "error_type": error_type, **extra}


# ----------------------------------------------------------------- detection
def test_coming_soon_page_is_not_a_redirect():
    html = ("<html><head><style>body{background-image:url('./img.jpg')}</style></head>"
            "<body><div>Coming Soon...</div></body></html>")
    assert detect_client_redirect(html) == (None, None)


def test_meta_refresh_any_attribute_order():
    a = '<meta http-equiv="refresh" content="0; url=https://new.com/x">'
    b = '<meta content="5;URL=\'https://new.com/y\'" HTTP-EQUIV=refresh>'
    assert detect_client_redirect(a) == ("meta_refresh", "https://new.com/x")
    assert detect_client_redirect(b) == ("meta_refresh", "https://new.com/y")


def test_meta_refresh_without_url_is_just_a_reload():
    assert detect_client_redirect('<meta http-equiv="refresh" content="30">') == (None, None)


def test_js_stub_redirect_detected():
    html = "<html><script>window.location.href = 'https://new.com/';</script></html>"
    assert detect_client_redirect(html) == ("js", "https://new.com/")
    assert detect_client_redirect("<script>location.replace('/home')</script>") == ("js", "/home")


def test_js_false_positives_are_ignored():
    big_text = "word " * 400
    page = f"<body>{big_text}<script>btn.onclick=()=>{{window.location.href='/x'}}</script></body>"
    assert detect_client_redirect(page) == (None, None)            # real page with a click handler
    assert detect_client_redirect("<script>var relocation = 'x'</script>") == (None, None)
    assert detect_client_redirect("<script>if (location == 'a') {}</script>") == (None, None)
    assert detect_client_redirect("<script>a.location = 'x'</script>") == (None, None)
    assert detect_client_redirect("<script>location.href = url + '?a=1'</script>") == (None, None)


# ------------------------------------------------------------------ counting
def test_single_200_hop_is_not_a_redirect():
    a = analyze_result(raw(f"{B}/p", [hop(f"{B}/p", 200)]))
    assert a["state"] == "ok"
    assert a["redirect_count"] == 0
    assert a["redirect_type"] == "none"
    assert a["final_url"] == f"{B}/p" and a["final_status"] == 200


def test_chain_counts_only_redirect_hops():
    a = analyze_result(raw(f"{B}/a", [hop(f"{B}/a", 301, f"{B}/b"),
                                      hop(f"{B}/b", 301, "/c"),
                                      hop(f"{B}/c", 200)]))
    assert a["state"] == "redirected" and a["redirect_count"] == 2
    assert a["final_url"] == f"{B}/c"
    assert any(f["code"] == "redirect_chain" for f in build_findings(a))


def test_external_and_temporary():
    a = analyze_result(raw(f"{B}/x", [hop(f"{B}/x", 302, "https://other.com/x"),
                                      hop("https://other.com/x", 200)]))
    assert a["redirect_type"] == "external" and a["first_redirect_status"] == 302
    codes = {f["code"] for f in build_findings(a)}
    assert {"redirect_external", "temporary_redirect"} <= codes


def test_www_and_http_to_https_is_internal():
    a = analyze_result(raw("http://site.com/", [hop("http://site.com/", 301, "https://www.site.com/"),
                                                hop("https://www.site.com/", 200)]))
    assert a["redirect_type"] == "internal" and a["redirect_count"] == 1


def test_loop_unreachable_broken_and_3xx_without_location():
    loop = analyze_result(raw(f"{B}/l1", [hop(f"{B}/l1", 301, f"{B}/l2"), hop(f"{B}/l2", 301, f"{B}/l1")]))
    assert loop["state"] == "loop" and loop["final_url"] is None

    dead = analyze_result(raw("https://nope.in/", [], "Connection failed.", "dns_failure"))
    assert dead["state"] == "unreachable" and dead["final_url"] is None
    assert build_findings(dead)[0]["code"] == "dns_failure"

    gone = analyze_result(raw(f"{B}/gone", [hop(f"{B}/gone", 404)]))
    assert gone["state"] == "broken"

    no_loc = analyze_result(raw(f"{B}/n", [hop(f"{B}/n", 301)]))
    assert no_loc["state"] == "broken" and no_loc["redirect_count"] == 0


# -------------------------------------------------------- client-side / browser
def test_browser_navigation_chain_counts_as_confirmed_client_redirect():
    a = analyze_result(raw("https://infomagine.com/", [hop("https://infomagine.com/", 200),
                                                       hop("https://infomagine.in/", 200)],
                           client_signal="js", browser_checked=True))
    assert a["state"] == "redirected" and a["redirect_count"] == 1
    assert a["client_redirect"] == "confirmed" and a["redirect_type"] == "external"
    f = [x for x in build_findings(a) if x["code"] == "client_side_redirect"][0]
    assert f["severity"] == "medium"


def test_signal_without_browser_is_only_suspected_and_not_counted():
    a = analyze_result(raw(f"{B}/", [hop(f"{B}/", 200, client_signal="meta_refresh",
                                         client_target="https://new.com/")]))
    assert a["client_redirect"] == "suspected" and a["redirect_count"] == 0
    f = [x for x in build_findings(a) if x["code"] == "client_side_redirect"][0]
    assert f["severity"] == "low"


def test_browser_saw_no_navigation_clears_false_positive():
    a = analyze_result(raw(f"{B}/", [hop(f"{B}/", 200)], client_signal="js", browser_checked=True))
    assert a["client_redirect"] is None and a["redirect_count"] == 0


# ------------------------------------------------------------ fetch_chain (mock)
def _client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=False)


def test_fetch_chain_records_hops_and_absolute_locations():
    def handler(req):
        if req.url.path == "/a":
            return httpx.Response(301, headers={"location": "/b"})
        return httpx.Response(200, headers={"content-type": "text/html"}, text="<html>ok</html>")

    async def go():
        async with _client(handler) as c:
            return await fetch_chain(c, f"{B}/a")
    r = asyncio.run(go())
    assert [h["status"] for h in r["hops"]] == [301, 200]
    assert r["hops"][0]["location"] == f"{B}/b"
    a = analyze_result(r)
    assert a["redirect_count"] == 1 and a["final_url"] == f"{B}/b"


def test_fetch_chain_flags_meta_refresh_but_not_coming_soon():
    def handler(req):
        if req.url.path == "/stub":
            return httpx.Response(200, headers={"content-type": "text/html"},
                                  text='<meta http-equiv="refresh" content="0;url=https://new.com/">')
        return httpx.Response(200, headers={"content-type": "text/html"},
                              text="<html><body>Coming Soon...</body></html>")

    async def go():
        async with _client(handler) as c:
            return (await fetch_chain(c, f"{B}/stub"), await fetch_chain(c, f"{B}/"))
    stub, home = asyncio.run(go())
    assert stub["hops"][0]["client_signal"] == "meta_refresh"
    assert "client_signal" not in home["hops"][0]


def test_validator_blocks_redirect_target_ssrf():
    def handler(req):
        return httpx.Response(302, headers={"location": "http://169.254.169.254/latest/meta-data"})

    async def validator(url):
        if "169.254" in url:
            raise BlockedURL(url)

    async def go():
        async with _client(handler) as c:
            return await fetch_chain(c, f"{B}/x", validator=validator)
    r = asyncio.run(go())
    assert r["error_type"] == "ssrf_blocked" and len(r["hops"]) == 1
    assert analyze_result(r)["state"] == "unreachable"


def test_max_hops_means_max_redirects_followed():
    def handler(req):
        n = int(req.url.path.strip("/") or 0)
        if n < 3:
            return httpx.Response(301, headers={"location": f"/{n + 1}"})
        return httpx.Response(200, text="end")

    async def go(m):
        async with _client(handler) as c:
            return analyze_result(await fetch_chain(c, f"{B}/0", max_hops=m))
    assert asyncio.run(go(3))["state"] == "redirected"
    assert asyncio.run(go(2))["state"] == "too_many_redirects"
    ok = asyncio.run(go(0))                       # max_hops=0 still fetches the first URL
    assert ok["state"] == "too_many_redirects" and len(ok["hops"]) == 1


# ------------------------------------------------------------ report / payload
def test_report_is_consistent_and_payload_is_slim():
    rep = build_report("site.com", [
        raw(f"{B}/ok", [hop(f"{B}/ok", 200)]),
        raw("https://nope.in/", [], "x", "dns_failure"),
        raw(f"{B}/a", [hop(f"{B}/a", 301, f"{B}/b"), hop(f"{B}/b", 200)]),
        raw(f"{B}/gone", [hop(f"{B}/gone", 404)]),
    ])
    s = rep["summary"]
    assert s["redirects_found"] == 1 and s["broken"] == 2
    assert s["by_status_class"] == {"ok": 1, "redirect": 1, "broken": 1, "unreachable": 1}
    assert rep["overall_status"] == "fail"
    allowed = {"url", "state", "redirect_count", "redirect_type", "final_url", "final_status",
               "error", "error_type", "client_redirect", "hops"}
    for r in rep["results"]:
        assert set(r) == allowed
        for h in r["hops"]:
            assert set(h) == {"url", "status", "location", "kind", "latency_ms"}
    assert public_result(analyze_result(raw(f"{B}/ok", [hop(f"{B}/ok", 200)])))["redirect_count"] == 0
