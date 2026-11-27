from __future__ import annotations

from typing import Any


def result_payload_is_incomplete(payload: Any) -> bool:
    """Detect reports with analyzed pages but no persisted rule checks."""
    if hasattr(payload, "model_dump"):
        payload = payload.model_dump()
    if not isinstance(payload, dict):
        return False

    audit = payload.get("audit")
    audit = audit if isinstance(audit, dict) else {}
    pages = audit.get("pages")
    pages = pages if isinstance(pages, dict) else {}
    summary = payload.get("summary")
    summary = summary if isinstance(summary, dict) else {}
    checks = summary.get("checks")
    checks = checks if isinstance(checks, dict) else {}
    analyzed_pages = pages.get("analyzed", 0)
    total_checks = checks.get("total")

    return (
        isinstance(analyzed_pages, (int, float))
        and analyzed_pages > 0
        and total_checks == 0
    )
