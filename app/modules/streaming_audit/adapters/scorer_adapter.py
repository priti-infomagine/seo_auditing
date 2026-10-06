from __future__ import annotations

from typing import Any

from app.modules.scorer.services.scorer_service import ScorerService


class ScorerAdapter:
    """Concrete adapter for page-level scoring using the existing scorer."""

    def __init__(self):
        self.scorer_service = ScorerService()

    async def score(self, parsed_data: dict[str, Any]) -> dict[str, Any]:
        score_report = await self.scorer_service.score_parsed_data(parsed_data)
        return score_report
