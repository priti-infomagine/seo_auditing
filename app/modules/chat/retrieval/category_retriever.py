from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.models.rule_evaluation_results import RuleEvaluationResult
from app.modules.audit.repositories.rule_evaluation_repository import RuleEvaluationResultRepository


class CategoryRetriever:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = RuleEvaluationResultRepository(db)

    async def get_category_failed_rules(self, project_id: UUID, category: str, limit: int = 20) -> list[dict]:
        results = await self.repo.get_by_category(project_id, category)
        failed = [r for r in results if not r.passed]
        failed.sort(key=lambda r: ({"critical": 0, "warning": 1, "error": 2}.get(r.severity, 3), r.rule_id))
        limited = failed[:limit]
        return [
            {
                "rule_id": r.rule_id,
                "rule_name": r.rule_name,
                "severity": r.severity,
                "message": r.message,
                "recommendation": r.recommendation,
                "page_url": (r.rule_data or {}).get("url") if isinstance(r.rule_data, dict) else None,
                "page_id": str(r.page_id),
                "score_impact": r.score_impact,
                "rule_data": r.rule_data or {},
            }
            for r in limited
        ]
