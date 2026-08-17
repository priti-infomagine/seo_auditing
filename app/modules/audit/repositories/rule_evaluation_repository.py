"""
RuleEvaluationResult repository - database operations for RuleEvaluationResult model.

Provides upsert for idempotency, ensuring no duplicate rule results for
the same (project_id, page_id, rule_id).
"""
from typing import List, Optional, Dict, Any
from uuid import UUID

from sqlalchemy import select, delete, func, cast, Integer
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.models.rule_evaluation_results import RuleEvaluationResult


class RuleEvaluationResultRepository:
    """Repository for RuleEvaluationResult database operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def upsert(self, result: RuleEvaluationResult) -> RuleEvaluationResult:
        """
        Insert or update a single RuleEvaluationResult for
        (project_id, page_id, rule_id).
        """
        existing = await self._get_existing(
            result.project_id, result.page_id, result.rule_id
        )
        if existing:
            existing.severity = result.severity
            existing.passed = result.passed
            existing.score_impact = result.score_impact
            existing.message = result.message
            existing.recommendation = result.recommendation
            existing.rule_data = result.rule_data
            existing.tags = result.tags
            existing.evaluated_at = result.evaluated_at
            self.db.add(existing)
            await self.db.flush()
            await self.db.refresh(existing)
            return existing
        self.db.add(result)
        await self.db.flush()
        await self.db.refresh(result)
        return result

    async def _get_existing(
        self,
        project_id: UUID,
        page_id: UUID,
        rule_id: str,
    ) -> Optional[RuleEvaluationResult]:
        """Find existing rule result for a page + rule."""
        result = await self.db.execute(
            select(RuleEvaluationResult).where(
                RuleEvaluationResult.project_id == project_id,
                RuleEvaluationResult.page_id == page_id,
                RuleEvaluationResult.rule_id == rule_id,
            )
        )
        return result.scalar_one_or_none()

    async def bulk_upsert(self, results: List[RuleEvaluationResult]) -> int:
        """
        Bulk insert or update RuleEvaluationResult rows.
        Returns number of rows processed.
        """
        if not results:
            return 0

        count = 0
        for result in results:
            existing = await self._get_existing(
                result.project_id, result.page_id, result.rule_id
            )
            if existing:
                existing.severity = result.severity
                existing.passed = result.passed
                existing.score_impact = result.score_impact
                existing.message = result.message
                existing.recommendation = result.recommendation
                existing.rule_data = result.rule_data
                existing.tags = result.tags
                existing.evaluated_at = result.evaluated_at
                self.db.add(existing)
            else:
                self.db.add(result)
            count += 1

        await self.db.flush()
        return count

    async def get_by_project_id(self, project_id: UUID) -> List[RuleEvaluationResult]:
        """Get all rule evaluation results for a project."""
        result = await self.db.execute(
            select(RuleEvaluationResult).where(
                RuleEvaluationResult.project_id == project_id
            ).order_by(RuleEvaluationResult.page_id, RuleEvaluationResult.rule_id)
        )
        return list(result.scalars().all())

    async def get_by_page_id(self, project_id: UUID, page_id: UUID) -> List[RuleEvaluationResult]:
        """Get all rule results for a specific page within a project."""
        result = await self.db.execute(
            select(RuleEvaluationResult).where(
                RuleEvaluationResult.project_id == project_id,
                RuleEvaluationResult.page_id == page_id,
            ).order_by(RuleEvaluationResult.rule_id)
        )
        return list(result.scalars().all())

    async def get_by_category(self, project_id: UUID, category: str) -> List[RuleEvaluationResult]:
        """Get all rule results for a specific category within a project."""
        result = await self.db.execute(
            select(RuleEvaluationResult).where(
                RuleEvaluationResult.project_id == project_id,
                RuleEvaluationResult.category == category,
            ).order_by(RuleEvaluationResult.page_id)
        )
        return list(result.scalars().all())

    async def get_summary(self, project_id: UUID) -> Dict[str, Any]:
        """Get aggregate counts for a project."""
        result = await self.db.execute(
            select(
                func.count().label("total"),
                func.sum(cast(RuleEvaluationResult.passed, Integer)).label("passed"),
                func.sum(cast(~RuleEvaluationResult.passed, Integer)).label("failed"),
                func.sum(
                    cast(
                        (RuleEvaluationResult.severity == "critical") & (~RuleEvaluationResult.passed),
                        Integer,
                    )
                ).label("critical"),
                func.sum(
                    cast(
                        (RuleEvaluationResult.severity == "warning") & (~RuleEvaluationResult.passed),
                        Integer,
                    )
                ).label("warnings"),
                func.sum(
                    cast(
                        (RuleEvaluationResult.severity == "error") & (~RuleEvaluationResult.passed),
                        Integer,
                    )
                ).label("errors"),
            ).where(RuleEvaluationResult.project_id == project_id)
        )
        row = result.mappings().first()
        if row is None:
            return {}
        return {
            "total": row["total"] or 0,
            "passed": row["passed"] or 0,
            "failed": row["failed"] or 0,
            "critical": row["critical"] or 0,
            "warnings": row["warnings"] or 0,
            "errors": row["errors"] or 0,
        }

    async def delete_by_project_id(self, project_id: UUID) -> int:
        """Delete all rule results for a project. Returns count deleted."""
        result = await self.db.execute(
            delete(RuleEvaluationResult).where(
                RuleEvaluationResult.project_id == project_id
            )
        )
        return result.rowcount
