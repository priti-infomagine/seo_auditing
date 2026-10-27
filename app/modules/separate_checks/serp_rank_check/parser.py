"""Parse a DataForSEO Google Organic SERP response into the rank result.

The stored ``result`` JSON shape:

.. code-block:: json

    {
      "found": true,
      "status": "found",
      "best_position": 7,
      "best_absolute_position": 9,
      "matches": [{"position": 7, "absolute_position": 9,
                   "url": "", "domain": "", "title": ""}],
      "serp_features": ["people_also_ask"],
      "top_results": [{"position": 1, "domain": "", "url": "",
                       "title": "", "snippet": ""}],
      "partial": false
    }

``found: false`` with ``best_position: null`` is a successful result,
not an error.  The ``status`` field distinguishes *why* a domain was
not found:
* ``found``                   — domain matched at least one organic result
* ``not_found_in_top_10``     — standard search (depth ≤ 10), no match
* ``not_found_within_limit``  — deep tracking (depth 100), no match
* ``no_target``               — no domain was supplied, only top results returned

``rank_absolute`` (the absolute organic position from DataForSEO's
response) is used for ``best_absolute_position`` and each match's
``absolute_position``.  ``rank_group`` (the position within a result
page) is used for ``position``.
"""
from __future__ import annotations

from typing import Any

import tldextract

from .exceptions import SerpParseError


def _registered_domain(url: Any) -> str:
    """Registrable domain (eTLD+1) of a URL string, or "" when unparseable."""
    if not isinstance(url, str) or not url:
        return ""
    try:
        return tldextract.extract(url).registered_domain.lower()
    except Exception:
        return ""


def _item_domain(item: dict[str, Any]) -> str:
    """Extract the registrable domain from a DataForSEO organic result item.

    DataForSEO returns a ``domain`` field on each organic item (e.g.
    ``"www.example.com"``).  We prefer that field — it is more
    reliable than re-parsing the URL — but fall back to extracting the
    registrable domain from ``url`` via *tldextract* when the field is
    absent or empty.
    """
    api_domain = item.get("domain")
    if isinstance(api_domain, str) and api_domain.strip():
        extracted = _registered_domain(api_domain)
        if extracted:
            return extracted
    url = item.get("url")
    return _registered_domain(url) if isinstance(url, str) else ""


def _item_description(item: dict[str, Any]) -> str:
    """Extract the result snippet/description from a DataForSEO organic item.

    DataForSEO's organic items use ``description`` for the result
    snippet text.  Older response snapshots or test fixtures may use
    ``snippet`` — we check both keys for compatibility.
    """
    desc = item.get("description")
    if isinstance(desc, str) and desc:
        return desc
    snip = item.get("snippet")
    if isinstance(snip, str) and snip:
        return snip
    return ""


def _extract_items(body: Any) -> list[dict[str, Any]]:
    if not isinstance(body, dict):
        raise SerpParseError("provider response is not a JSON object")
    tasks = body.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise SerpParseError("provider response has no tasks")
    task = tasks[0]
    if not isinstance(task, dict):
        raise SerpParseError("provider response has an invalid task")
    results = task.get("result")
    if not isinstance(results, list) or not results:
        raise SerpParseError("provider response has no result")
    first = results[0]
    if not isinstance(first, dict):
        raise SerpParseError("provider response has an invalid result")
    items = first.get("items")
    if items is None:
        return []
    if not isinstance(items, list):
        raise SerpParseError("provider response has an invalid items list")
    return [item for item in items if isinstance(item, dict)]


def parse_serp_response(
    body: dict[str, Any],
    target_domain: str | None,
    depth: int,
    top_results_limit: int | None = None,
    deep_tracking: bool = False,
) -> dict[str, Any]:
    """Build the rank result from a raw provider response body.

    When *target_domain* is ``None`` (no domain supplied), the parser
    returns only ``top_results`` with ``found=False`` and
    ``status="no_target"`` — no domain matching is attempted.

    *depth* controls both how many ``top_results`` are returned and
    the ``partial`` flag.  When *top_results_limit* is provided it
    overrides *depth* for capping ``top_results`` only.
    """
    items = _extract_items(body)

    if target_domain is not None:
        target = _registered_domain(target_domain)
        if not target:
            raise SerpParseError("invalid target domain")
    else:
        target = None

    organic = [
        item
        for item in items
        if item.get("type") == "organic"
    ]
    organic.sort(
        key=lambda item: (
            item.get("rank_group")
            if isinstance(item.get("rank_group"), int)
            else item.get("rank_absolute")
            if isinstance(item.get("rank_absolute"), int)
            else 0
        )
    )

    matches: list[dict[str, Any]] = []
    if target is not None:
        for item in organic:
            url = item.get("url")
            if not isinstance(url, str) or not url:
                continue
            item_domain = _item_domain(item)
            if item_domain == target:
                matches.append(
                    {
                        "position": item.get("rank_group"),
                        "absolute_position": item.get("rank_absolute"),
                        "url": url,
                        "domain": item_domain,
                        "title": item.get("title") or "",
                    }
                )

    if target is None:
        status = "no_target"
    elif matches:
        status = "found"
    elif deep_tracking:
        status = "not_found_within_limit"
    else:
        status = "not_found_in_top_10"

    features = sorted(
        {
            item["type"]
            for item in items
            if isinstance(item.get("type"), str)
            and item["type"] != "organic"
        }
    )

    limit = top_results_limit if top_results_limit is not None else depth

    top_results: list[dict[str, Any]] = []
    for item in organic[:limit]:
        url = item.get("url")
        url = url if isinstance(url, str) else ""
        top_results.append(
            {
                "position": item.get("rank_group"),
                "domain": _item_domain(item),
                "url": url,
                "title": item.get("title") or "",
                "snippet": _item_description(item),
            }
        )

    best = matches[0] if matches else None
    return {
        "found": bool(matches),
        "status": status,
        "best_position": best["position"] if best else None,
        "best_absolute_position": best["absolute_position"] if best else None,
        "matches": matches,
        "serp_features": features,
        "top_results": top_results,
        "partial": len(organic) < depth,
    }
