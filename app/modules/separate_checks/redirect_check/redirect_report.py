"""Standalone redirect-chain analysis module (single source of truth).

  - fetch_chain():            HTTP fetching that never auto-follows redirects, records every
                              hop, validates every hop target (SSRF hook) and flags
                              client-side (meta refresh / JS) redirect signals.
  - detect_client_redirect(): precise meta-refresh / tiny-JS-stub detector (decides when the
                              Chromium fallback is worth launching).
  - analyze_result():         puts each URL into exactly ONE state
                              (ok | redirected | broken | unreachable | loop | too_many_redirects)
                              and counts redirects = 3xx hops with Location + confirmed
                              client-side navigations. The final 200 is never a redirect.
  - build_findings():         findings with real fix text and a correct where_to_fix.
  - public_result():          the slim per-URL payload returned by the API.
  - probe_soft_404():         optional catch-all / SPA probe.
  - build_report():           full report; summary is derived from the same states.

Wired into: celery task -> service._execute -> SSE -> DB persistence -> router.
"""
from __future__ import annotations

import asyncio
import re
import socket
import ssl
import time
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from urllib.parse import urljoin, urlsplit

import httpx

REDIRECT_CODES = {301, 302, 303, 307, 308}
TEMPORARY_CODES = {302, 303, 307}
SEV_RANK = {"low": 1, "medium": 2, "high": 3}
BROKEN_STATES = {"broken", "unreachable", "loop", "too_many_redirects"}


class BlockedURL(Exception):
    """Raised by a validator when a hop target must not be requested (SSRF)."""


# --------------------------------------------------------------------------
# client-side redirect detection (meta refresh / JS location stub)
# --------------------------------------------------------------------------
_MAX_HTML_SNIFF_BYTES = 200_000
_MAX_STUB_TEXT_CHARS = 300     # a JS redirect stub has (almost) no visible text

_META_TAG_RE = re.compile(r"<meta\b[^>]*>", re.I)
_META_REFRESH_RE = re.compile(r"http-equiv\s*=\s*['\"]?\s*refresh\b", re.I)
_META_CONTENT_RE = re.compile(r"content\s*=\s*(['\"])(.*?)\1", re.I | re.S)
_META_URL_RE = re.compile(r"url\s*=\s*['\"]?\s*([^'\";\s]+)", re.I)

# `location = "x"`, `window.location.href = 'x'` ...   (not `a.location`, `relocation`, `==`)
_JS_ASSIGN_RE = re.compile(
    r"(?<![\w$.])(?:(?:window|self|top|document)\s*\.\s*)?location"
    r"(?:\s*\.\s*href)?\s*=(?!=)\s*(['\"])([^'\"]+)\1", re.I)
# `location.replace("x")`, `window.location.assign('x')`
_JS_CALL_RE = re.compile(
    r"(?<![\w$.])(?:(?:window|self|top|document)\s*\.\s*)?location"
    r"\s*\.\s*(?:replace|assign)\s*\(\s*(['\"])([^'\"]+)\1", re.I)
_SCRIPT_STYLE_RE = re.compile(r"<(script|style|noscript)\b.*?</\1\s*>", re.I | re.S)
_TAG_RE = re.compile(r"<[^>]+>")


def detect_client_redirect(html: str) -> tuple[str | None, str | None]:
    """Return (signal, target) where signal is "meta_refresh" | "js" | None.

    * meta refresh needs a ``url=`` target (a plain reload is not a redirect).
    * a JS redirect only counts when the page is a stub (almost no visible text) and
      the target is a string literal - a full page with a click handler that sets
      ``location.href`` is NOT a redirect.
    """
    for tag in _META_TAG_RE.findall(html):
        if _META_REFRESH_RE.search(tag):
            content = _META_CONTENT_RE.search(tag)
            target = _META_URL_RE.search(content.group(2)) if content else None
            if target:
                return "meta_refresh", target.group(1)

    visible = _TAG_RE.sub(" ", _SCRIPT_STYLE_RE.sub(" ", html))
    if len(" ".join(visible.split())) <= _MAX_STUB_TEXT_CHARS:
        for rx in (_JS_ASSIGN_RE, _JS_CALL_RE):
            m = rx.search(html)
            if m:
                return "js", m.group(2)
    return None, None


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def host_of(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower().rstrip(".")
    return host[4:] if host.startswith("www.") else host


def _url_key(url: str | None) -> str:
    if not url:
        return ""
    p = urlsplit(url)
    return f"{p.scheme}://{(p.hostname or '').lower()}{p.path.rstrip('/') or '/'}?{p.query}"


def classify_error(exc: BaseException) -> str:
    """Walk the exception chain and return a specific error type."""
    chain, e = [], exc
    while e is not None and e not in chain:
        chain.append(e)
        e = e.__cause__ or e.__context__
    for e in chain:
        name = type(e).__name__
        if isinstance(e, BlockedURL):
            return "ssrf_blocked"
        if isinstance(e, socket.gaierror):
            return "dns_failure"
        if isinstance(e, ssl.SSLError):
            return "tls_error"
        if isinstance(e, ConnectionRefusedError):
            return "connection_refused"
        if isinstance(e, TimeoutError) or "Timeout" in name:
            return "timeout"
        if name == "TooManyRedirects":
            return "too_many_redirects"
    return "connection_failed"


# --------------------------------------------------------------------------
# fetching (httpx). Never auto-follow, record every hop.
# --------------------------------------------------------------------------
async def fetch_chain(
    client: httpx.AsyncClient,
    url: str,
    max_hops: int = 10,
    validator: Callable[[str], Awaitable[None]] | None = None,
) -> dict:
    """Follow redirects manually. ``max_hops`` = max number of REDIRECTS followed
    (so up to ``max_hops + 1`` requests). ``validator`` is awaited before EVERY
    request, including redirect targets, and must raise BlockedURL to refuse."""
    hops, seen, current = [], set(), url
    try:
        for _ in range(max_hops + 1):
            if current in seen:
                break
            seen.add(current)
            if validator is not None:
                await validator(current)
            t0 = time.perf_counter()
            r = await client.get(current, follow_redirects=False)
            ms = int((time.perf_counter() - t0) * 1000)
            loc = r.headers.get("location")
            hop = {
                "url": current,
                "status": r.status_code,
                "location": urljoin(current, loc) if loc else None,
                "latency_ms": ms,
            }
            ct = r.headers.get("content-type", "").lower()
            if r.status_code == 200 and ("text/html" in ct or "application/xhtml+xml" in ct):
                try:
                    html = r.content[:_MAX_HTML_SNIFF_BYTES].decode(r.encoding or "utf-8", "ignore")
                    signal, target = detect_client_redirect(html)
                    if signal:
                        hop["client_signal"] = signal
                        hop["client_target"] = urljoin(current, target) if target else None
                except Exception:  # noqa: BLE001 - sniffing must never break the check
                    pass
            hops.append(hop)
            if r.status_code in REDIRECT_CODES and hop["location"]:
                current = hop["location"]
                continue
            break
    except Exception as exc:  # noqa: BLE001
        return {"url": url, "hops": hops,
                "error": str(exc) or type(exc).__name__,
                "error_type": classify_error(exc)}
    return {"url": url, "hops": hops, "error": None, "error_type": None}


# --------------------------------------------------------------------------
# analysis of ONE url
# --------------------------------------------------------------------------
def _normalize_hops(raw_hops: list[dict]) -> list[dict]:
    """Copy hops into one shape and mark how each one leaves the page:
    kind="http"   -> 3xx with a Location header
    kind="client" -> a non-error hop followed by a hop on a different URL
                     (only a real browser navigation chain can produce this)."""
    hops = []
    for h in raw_hops:
        loc = h.get("location") or h.get("resolved")
        hops.append({
            "url": h["url"],
            "status": h.get("status"),
            "location": urljoin(h["url"], loc) if loc else None,
            "kind": None,
            "latency_ms": h.get("latency_ms", h.get("latencyMs")),
            "client_signal": h.get("client_signal"),
            "client_target": h.get("client_target"),
        })
    for i, h in enumerate(hops):
        status = h["status"]
        if status in REDIRECT_CODES and h["location"]:
            h["kind"] = "http"
        elif (i < len(hops) - 1 and (status is None or status < 400)
              and _url_key(hops[i + 1]["url"]) != _url_key(h["url"])):
            h["kind"] = "client"
            h["location"] = hops[i + 1]["url"]
    return hops


def analyze_result(raw: dict) -> dict:
    start = raw["url"]
    hops = _normalize_hops(raw.get("hops") or [])
    error, error_type = raw.get("error"), raw.get("error_type")

    redirect_hops = [h for h in hops if h["kind"]]
    last = hops[-1] if hops else None
    ends_in_redirect = bool(last and last["kind"] == "http")
    loop = bool(ends_in_redirect
                and _url_key(last["location"]) in {_url_key(h["url"]) for h in hops})

    # final status/url only exist if the chain ended in a real response
    if error or ends_in_redirect or not last:
        final_status, final_url = None, None
    else:
        final_status, final_url = last["status"], last["url"]

    if error or not hops:
        state = "unreachable"
    elif loop:
        state = "loop"
    elif ends_in_redirect:
        state = "too_many_redirects"
    elif final_status is not None and final_status >= 300:
        state = "broken"          # 4xx/5xx, or a 3xx without a Location header
    elif redirect_hops:
        state = "redirected"
    else:
        state = "ok"

    redirect_count = len(redirect_hops)
    target = final_url or (redirect_hops[-1]["location"] if redirect_hops else None)
    if redirect_count == 0 or not target:
        redirect_type = "none"
    else:
        redirect_type = "external" if host_of(target) != host_of(start) else "internal"

    # client-side redirect: confirmed by a browser navigation, or only suspected
    signal_hop = next((h for h in hops if h.get("client_signal")), None)
    client_signal = (signal_hop or {}).get("client_signal") or raw.get("client_signal")
    client_target = (signal_hop or {}).get("client_target") or raw.get("client_target")
    if any(h["kind"] == "client" for h in redirect_hops):
        client_redirect = "confirmed"
    elif client_signal and not raw.get("browser_checked"):
        client_redirect = "suspected"
    else:
        client_redirect = None     # signal seen, but a real browser did not navigate

    return {
        "url": start,
        "state": state,
        "error": error,
        "error_type": error_type or ("no_response" if state == "unreachable" else None),
        "redirect_count": redirect_count,
        "redirect_type": redirect_type,
        "final_url": final_url,
        "final_status": final_status,
        "client_redirect": client_redirect,
        "client_signal": client_signal,
        "client_target": client_target,
        "first_redirect_status": (redirect_hops[0]["status"]
                                  if redirect_hops and redirect_hops[0]["kind"] == "http" else None),
        "insecure": (urlsplit(start).scheme == "https" and bool(final_url)
                     and urlsplit(final_url).scheme == "http"),
        "is_loop": loop,
        "hops": hops,
        "source_pages": raw.get("source_pages") or [],
    }


def public_result(a: dict) -> dict:
    """The slim per-URL payload exposed by the API (no duplicate or internal fields)."""
    return {
        "url": a["url"],
        "state": a["state"],
        "redirect_count": a["redirect_count"],
        "redirect_type": a["redirect_type"],
        "final_url": a["final_url"],
        "final_status": a["final_status"],
        "error": a["error"],
        "error_type": a["error_type"],
        "client_redirect": a["client_redirect"],
        "hops": [{k: h[k] for k in ("url", "status", "location", "kind", "latency_ms")}
                 for h in a["hops"]],
    }


# --------------------------------------------------------------------------
# findings for ONE analyzed url
# --------------------------------------------------------------------------
_ERROR_ADVICE = {
    "dns_failure": ("DNS lookup failed (domain does not resolve).",
                    "Check the domain is registered and has A/AAAA/CNAME records.",
                    "dns_or_domain_registration"),
    "connection_refused": ("Connection refused by the server.",
                           "Make sure the web server listens on 80/443 and the firewall allows it.",
                           "server_or_firewall"),
    "timeout": ("Request timed out.",
                "Check server load, firewall rules and network path to the host.",
                "server_or_network"),
    "tls_error": ("TLS/SSL handshake failed.",
                  "Install a valid certificate that covers this hostname and is not expired.",
                  "ssl_certificate"),
    "too_many_redirects": ("Redirect limit exceeded.",
                           "Flatten the chain so the URL reaches its target in one hop.",
                           "redirect_rules"),
    "ssrf_blocked": ("A URL in the chain points to a blocked/internal address.",
                     "Remove redirects to private, loopback or link-local hosts.",
                     "redirect_rules"),
    "browser_error": ("The browser check failed.",
                      "Retry; if it keeps failing, test the URL manually in a browser.",
                      "server_or_network"),
    "connection_failed": ("Could not connect for an unknown reason.",
                          "Retry and inspect the raw exception for the real cause.",
                          "server_or_network"),
    "no_response": ("No response was received.",
                    "Retry and inspect the raw exception for the real cause.",
                    "server_or_network"),
}


def build_findings(r: dict) -> list[dict]:
    url, out = r["url"], []

    def add(code, severity, message, evidence, fix, where):
        out.append({"code": code, "severity": severity,
                    "status": "fail" if severity == "high" else "warning",
                    "message": message, "evidence": evidence, "target_url": url,
                    "redirect_count": r["redirect_count"],
                    "final_status": r["final_status"],
                    "recommendation": {"fix": fix, "where_to_fix": where}})

    state, hops = r["state"], r["hops"]
    path = " -> ".join([h["url"] for h in hops])

    if state == "unreachable":
        etype = r["error_type"]
        what, fix, where = _ERROR_ADVICE.get(etype, _ERROR_ADVICE["connection_failed"])
        add(etype if etype in _ERROR_ADVICE else "unreachable", "high",
            f"URL is unreachable: {url}", f"{what} ({r['error']})", fix, where)
    elif state == "loop":
        add("redirect_loop", "high", f"Redirect loop starting at {url}",
            f"{path} -> {hops[-1]['location']}",
            "Remove or correct the rule that sends the URL back into the chain.",
            "redirect_rules")
    elif state == "too_many_redirects":
        add("too_many_redirects", "high", f"Too many redirects from {url}",
            f"{r['redirect_count']} hops without a final response",
            "Flatten the chain so the URL reaches its target in one hop.",
            "redirect_rules")
    elif state == "broken":
        fs = r["final_status"]
        add("broken_link", "high", f"URL ends in HTTP {fs}: {url}",
            f"final status {fs} at {hops[-1]['url']}",
            "Restore the page, or 301 it to the best replacement, and update links to it.",
            "source_pages" if r["source_pages"] else "server_config")

    if r["redirect_count"] > 1 and state in {"redirected", "broken"}:
        add("redirect_chain", "medium",
            f"Redirect chain ({r['redirect_count']} hops) for {url}", path,
            f"Redirect {url} straight to {r['final_url'] or hops[-1]['url']} in one hop.",
            "redirect_rules")

    if r["first_redirect_status"] in TEMPORARY_CODES:
        add("temporary_redirect", "low",
            f"Temporary redirect ({r['first_redirect_status']}) for {url}",
            f"first hop status {r['first_redirect_status']}",
            "If the move is permanent, use 301 (or 308 to keep the HTTP method).",
            "redirect_rules")

    if r["client_redirect"]:
        how = {"meta_refresh": "meta refresh tag", "js": "JavaScript redirect"}.get(
            r["client_signal"], "client-side redirect")
        confirmed = r["client_redirect"] == "confirmed"
        add("client_side_redirect", "medium" if confirmed else "low",
            f"{'Client-side redirect' if confirmed else 'Possible client-side redirect'} for {url}",
            f"{how}" + (f" -> {r['client_target']}" if r["client_target"] else "")
            + ("" if confirmed else " (not verified in a browser)"),
            "Replace it with a server-side 301 redirect so search engines pass link equity.",
            "server_config")

    if r["redirect_type"] == "internal" and r["redirect_count"] == 1 and r["source_pages"]:
        add("redirect_internal", "low", f"Internal links point to a redirecting URL: {url}",
            f"{url} -> {r['final_url']}",
            f"Update internal links to {r['final_url']} to save a hop.", "source_pages")

    if r["redirect_type"] == "external":
        target = r["final_url"] or hops[-1]["location"]
        add("redirect_external", "low", f"Redirect leaves the host for {url}",
            f"{host_of(url)} -> {host_of(target)}",
            "Confirm the host change is intended; update links to the final URL.",
            "source_pages" if r["source_pages"] else "redirect_rules")

    if r["insecure"]:
        add("https_downgrade", "medium", f"HTTPS downgraded to HTTP for {url}",
            f"{url} -> {r['final_url']}",
            "Redirect to the https:// version of the target.", "redirect_rules")

    return out


# --------------------------------------------------------------------------
# optional: soft-404 probe (catch-all SPA / wrong server config)
# --------------------------------------------------------------------------
async def probe_soft_404(client: httpx.AsyncClient, base_url: str) -> list[dict]:
    fake = urljoin(base_url, f"/{uuid.uuid4().hex}-not-found")
    r = await client.get(fake, follow_redirects=False)
    if r.status_code == 200:
        return [{
            "code": "soft_404", "severity": "medium", "status": "warning",
            "message": "Server returns 200 for a URL that cannot exist",
            "evidence": f"{fake} -> 200 (content-length {r.headers.get('content-length')}, "
                        f"etag {r.headers.get('etag')})",
            "target_url": fake, "redirect_count": 0, "final_status": 200,
            "recommendation": {"fix": "Return a real 404 for unknown routes (server rewrite rules "
                                      "or SPA server-side route validation).",
                               "where_to_fix": "server_config"}}]
    return []


# --------------------------------------------------------------------------
# full report
# --------------------------------------------------------------------------
def build_report(domain: str, raw_results: list[dict],
                 extra_findings: list[dict] | None = None) -> dict:
    analyzed = [analyze_result(r) for r in raw_results]
    findings = [f for a in analyzed for f in build_findings(a)] + (extra_findings or [])

    states = [a["state"] for a in analyzed]
    summary = {
        "total_urls": len(analyzed),
        "redirects_found": sum(a["redirect_count"] > 0 for a in analyzed),
        "redirect_chains": sum(a["redirect_count"] > 1 and a["state"] == "redirected"
                               for a in analyzed),
        "broken": sum(s in BROKEN_STATES for s in states),
        "internal_redirects": sum(a["redirect_type"] == "internal" for a in analyzed),
        "external_redirects": sum(a["redirect_type"] == "external" for a in analyzed),
        "loops": sum(a["is_loop"] for a in analyzed),
        "client_redirects": sum(a["client_redirect"] is not None for a in analyzed),
        "insecure": sum(a["insecure"] for a in analyzed),
        "by_status_class": {
            "ok": states.count("ok"),
            "redirect": states.count("redirected"),
            "broken": sum(s in {"broken", "loop", "too_many_redirects"} for s in states),
            "unreachable": states.count("unreachable"),
        },
    }

    # one recommendation per code, with how many URLs are affected
    recs: dict[str, dict] = {}
    for f in findings:
        rec_data = f.get("recommendation") or {}
        rec = recs.setdefault(f["code"], {
            "code": f["code"], "priority": f["severity"],
            "title": f["message"].split(":")[0],
            "fix": rec_data.get("fix", ""),
            "where_to_fix": rec_data.get("where_to_fix", "server_config"),
            "affected_count": 0, "examples": []})
        rec["affected_count"] += 1
        if len(rec["examples"]) < 3:
            rec["examples"].append(f["evidence"])

    top = max((SEV_RANK[f["severity"]] for f in findings), default=0)
    return {
        "check_id": str(uuid.uuid4()),
        "domain": domain,
        "status": "completed",
        "total_checked": len(analyzed),
        "results": [public_result(a) for a in analyzed],
        "findings": findings,
        "recommendations": sorted(recs.values(), key=lambda x: -SEV_RANK[x["priority"]]),
        "summary": summary,
        "overall_status": "ok" if top == 0 else ("warning" if top < 3 else "fail"),
        "severity": {0: "none", 1: "low", 2: "medium", 3: "high"}[top],
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


async def run_check(client: httpx.AsyncClient, domain: str, urls: list[str],
                    soft_404: bool = True, max_hops: int = 10,
                    validator: Callable[[str], Awaitable[None]] | None = None) -> dict:
    sem = asyncio.Semaphore(10)

    async def one(u):
        async with sem:
            return await fetch_chain(client, u, max_hops=max_hops, validator=validator)

    raw = await asyncio.gather(*(one(u) for u in urls))
    extra = await probe_soft_404(client, f"https://{domain}/") if soft_404 else []
    return build_report(domain, list(raw), extra)
