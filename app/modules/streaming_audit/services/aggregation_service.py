from __future__ import annotations

from typing import Any


class AggregationService:
    """Aggregate page-level streaming results into audit-level summaries."""

    def aggregate(self, page_results: list[dict[str, Any]]) -> dict[str, Any]:
        completed = [item for item in page_results if item.get("status") == "completed"]
        failed = [item for item in page_results if item.get("status") != "completed"]
        scores = [item.get("page_score") for item in completed if item.get("page_score") is not None]

        aggregated_score = 0.0
        if scores:
            aggregated_score = round(sum(scores) / len(scores), 2)

        return {
            "status": "completed" if page_results else "queued",
            "total_pages": len(page_results),
            "completed_count": len(completed),
            "failed_count": len(failed),
            "overall_score": aggregated_score,
            "page_scores": scores,
        }
