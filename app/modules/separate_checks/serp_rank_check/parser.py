"""Parse a DataForSEO Google Organic SERP response into the rank result.

The stored ``result`` JSON shape:

.. code-block:: json

    {
      "found": true,
      "best_position": 7,
      "best_absolute_position": 9,
      "matches": [{"position": 7, "absolute_position": 9,
                   "url": "", "title": ""}],
      "serp_features": ["people_also_ask"],
      "top_results": [{"position": 1, "domain": "", "url": "",
                       "title": "", "snippet": ""}],
      "partial": false
    }

``found: false`` with ``best_position: null`` is a successful result,
not an error.
"""
from __future__ import annotations

from typing import Any

import tldextract

from .exceptions import SerpParseError


def _registered_domain(url: Any) -> str:
    """Registrable domain (eTLD+1) of a URL, or "" when unparseable."""
    if not isinstance(url, str) or not url:
        return ""
    try:
        return tldextract.extract(url).registered_domain.lower()
    except Exception:
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
    target_domain: str,
    depth: int,
    top_results_limit: int,
) -> dict[str, Any]:
    """Build the rank result from a raw provider response body."""
    items = _extract_items(body)

    target = _registered_domain(target_domain)
    if not target:
        raise SerpParseError("invalid target domain")

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
    for item in organic:
        url = item.get("url")
        if not isinstance(url, str) or not url:
            continue
        if _registered_domain(url) == target:
            matches.append(
                {
                    "position": item.get("rank_group"),
                    "absolute_position": item.get("rank_absolute"),
                    "url": url,
                    "title": item.get("title") or "",
                }
            )

    features = sorted(
        {
            item["type"]
            for item in items
            if isinstance(item.get("type"), str)
            and item["type"] != "organic"
        }
    )

    top_results: list[dict[str, Any]] = []
    for item in organic[:top_results_limit]:
        url = item.get("url")
        url = url if isinstance(url, str) else ""
        top_results.append(
            {
                "position": item.get("rank_group"),
                "domain": _registered_domain(url),
                "url": url,
                "title": item.get("title") or "",
                "snippet": item.get("snippet") or "",
            }
        )

    best = matches[0] if matches else None
    return {
        "found": bool(matches),
        "best_position": best["position"] if best else None,
        "best_absolute_position": best["absolute_position"] if best else None,
        "matches": matches,
        "serp_features": features,
        "top_results": top_results,
        "partial": len(organic) < depth,
    }
