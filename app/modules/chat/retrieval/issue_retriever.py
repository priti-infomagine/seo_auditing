from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.models.rule_evaluation_results import RuleEvaluationResult
from app.modules.audit.repositories.rule_evaluation_repository import RuleEvaluationResultRepository


class IssueRetriever:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = RuleEvaluationResultRepository(db)
    
    async def get_failed_issues(
        self,
        project_id: UUID,
        category: Optional[str] = None,
        page_url: Optional[str] = None,
        rule_id: Optional[str] = None,
        limit: int = 20,
    ) -> list[dict]:
        results = await self.repo.get_by_project_id(project_id)
        failed = [r for r in results if not r.passed]
        if category:
            failed = [r for r in failed if r.category == category]
        if rule_id:
            failed = [r for r in failed if r.rule_id == rule_id]
        if page_url:
            failed = [r for r in failed if (r.rule_data or {}).get("url") == page_url]
        failed.sort(key=lambda r: ({"critical": 0, "warning": 1, "error": 2}.get(r.severity, 3), r.rule_id))
        limited = failed[:limit]
        return [
            {
                "rule_id": r.rule_id,
                "rule_name": r.rule_name,
                "category": r.category,
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
