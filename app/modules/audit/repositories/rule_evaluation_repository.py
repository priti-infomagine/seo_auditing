"""
RuleEvaluationResult repository - database operations for RuleEvaluationResult model.

Provides upsert for idempotency, ensuring no duplicate rule results for
the same (audit_id, page_id, rule_id).
"""
from typing import List, Optional, Dict, Any, Set, Tuple
from uuid import UUID

from sqlalchemy import select, delete, func, cast, Integer
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.models.rule_evaluation_results import RuleEvaluationResult


class RuleEvaluationResultRepository:
    """Repository for RuleEvaluationResult database operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def upsert(self, result: RuleEvaluationResult) -> RuleEvaluationResult:
        """
        Insert or update a single RuleEvaluationResult for
        (audit_id, page_id, rule_id).
        """
        existing = await self._get_existing(
            result.audit_id, result.page_id, result.rule_id
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
        audit_id: UUID,
        page_id: UUID,
        rule_id: str,
    ) -> Optional[RuleEvaluationResult]:
        """Find existing rule result for a page + rule."""
        result = await self.db.execute(
            select(RuleEvaluationResult).where(
                RuleEvaluationResult.audit_id == audit_id,
                RuleEvaluationResult.page_id == page_id,
                RuleEvaluationResult.rule_id == rule_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_existing_page_ids(
        self, audit_id: UUID, page_ids: List[UUID]
    ) -> Set[UUID]:
        """
        Return the set of page_ids (within an audit) that already have rule
        evaluation results. Single query — replaces per-page `get_by_page_id`
        loops (N+1) in the evaluate stage.
        """
        if not page_ids:
            return set()
        rows = await self.db.execute(
            select(RuleEvaluationResult.page_id).where(
                RuleEvaluationResult.audit_id == audit_id,
                RuleEvaluationResult.page_id.in_(page_ids),
            )
        )
        return {row[0] for row in rows.all()}

    async def bulk_upsert(self, results: List[RuleEvaluationResult]) -> int:
        """
        True bulk upsert of RuleEvaluationResult rows in batched statements.

        Uses PostgreSQL `INSERT ... ON CONFLICT
        (audit_id, page_id, rule_id) DO UPDATE`. The unique constraint
        `uq_rule_results_audit_page_rule` (added in the
        a1b2c3d4 migration) backs the conflict target. Replaces the
        previous per-row SELECT+UPDATE loop.

        Batches inserts to stay under PostgreSQL's 32767 parameter limit
        (each row has 14 columns; max ~2184 rows per batch).

        Returns number of rows processed.
        """
        if not results:
            return 0

        # Each row has 14 columns; PostgreSQL max is 32767 parameters.
        # Use 500 rows per batch = 7000 params (well under the limit).
        BATCH_SIZE = 500
        total_processed = 0

        for start in range(0, len(results), BATCH_SIZE):
            batch = results[start : start + BATCH_SIZE]
            rows = []
            for r in batch:
                rows.append({
                    "id": r.id,
                    "audit_id": r.audit_id,
                    "page_id": r.page_id,
                    "rule_id": r.rule_id,
                    "rule_name": r.rule_name,
                    "category": r.category,
                    "severity": r.severity,
                    "passed": r.passed,
                    "score_impact": r.score_impact,
                    "message": r.message,
                    "recommendation": r.recommendation,
                    "rule_data": r.rule_data,
                    "tags": r.tags,
                    "evaluated_at": r.evaluated_at,
                })

            stmt = pg_insert(RuleEvaluationResult).values(rows)
            stmt = stmt.on_conflict_do_update(
                index_elements=["audit_id", "page_id", "rule_id"],
                set_={
                    "rule_name": stmt.excluded.rule_name,
                    "category": stmt.excluded.category,
                    "severity": stmt.excluded.severity,
                    "passed": stmt.excluded.passed,
                    "score_impact": stmt.excluded.score_impact,
                    "message": stmt.excluded.message,
                    "recommendation": stmt.excluded.recommendation,
                    "rule_data": stmt.excluded.rule_data,
                    "tags": stmt.excluded.tags,
                    "evaluated_at": stmt.excluded.evaluated_at,
                },
            )
            await self.db.execute(stmt)
            await self.db.flush()
            total_processed += len(rows)

        return total_processed

    async def get_by_audit_id(self, audit_id: UUID) -> List[RuleEvaluationResult]:
        """Get all rule evaluation results for an audit (== crawl_id)."""
        result = await self.db.execute(
            select(RuleEvaluationResult).where(
                RuleEvaluationResult.audit_id == audit_id
            ).order_by(RuleEvaluationResult.page_id, RuleEvaluationResult.rule_id)
        )
        return list(result.scalars().all())

    async def get_by_page_id(self, audit_id: UUID, page_id: UUID) -> List[RuleEvaluationResult]:
        """Get all rule results for a specific page within an audit."""
        result = await self.db.execute(
            select(RuleEvaluationResult).where(
                RuleEvaluationResult.audit_id == audit_id,
                RuleEvaluationResult.page_id == page_id,
            ).order_by(RuleEvaluationResult.rule_id)
        )
        return list(result.scalars().all())

    async def get_by_category(self, audit_id: UUID, category: str) -> List[RuleEvaluationResult]:
        """Get all rule results for a specific category within an audit."""
        result = await self.db.execute(
            select(RuleEvaluationResult).where(
                RuleEvaluationResult.audit_id == audit_id,
                RuleEvaluationResult.category == category,
            ).order_by(RuleEvaluationResult.page_id)
        )
        return list(result.scalars().all())

    async def get_failed_by_audit_id(
        self, audit_id: UUID
    ) -> List[RuleEvaluationResult]:
        """
        Failed rule results for an audit — additive to ``get_by_audit_id``.

        Single SQL query that returns full ``RuleEvaluationResult`` rows.
        Keeps the overview payload build off per-page fetches (no N+1) and
        remains compatible with SQLAlchemy's ``scalars()`` row mapping.
        """
        stmt = (
            select(RuleEvaluationResult)
            .where(
                RuleEvaluationResult.audit_id == audit_id,
                RuleEvaluationResult.passed == False,  # noqa: E712
            )
            .order_by(
                RuleEvaluationResult.rule_id,
                RuleEvaluationResult.evaluated_at,
            )
        )
        rows = (await self.db.execute(stmt)).scalars().all()
        return list(rows)

    async def list_failed_by_audit_id_paginated(
        self,
        audit_id: UUID,
        *,
        category: Optional[str] = None,
        severity: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> Tuple[List[RuleEvaluationResult], int]:
        """
        Paginated rule results for the compact issue list endpoint.

        ``status`` filter: 'failed' (default), 'passed', or None (= failed).
        Returns ``(rows, total)``.
        """
        base = select(RuleEvaluationResult).where(
            RuleEvaluationResult.audit_id == audit_id,
        )
        if status == "passed":
            base = base.where(RuleEvaluationResult.passed == True)  # noqa: E712
        else:
            base = base.where(RuleEvaluationResult.passed == False)  # noqa: E712
        if category:
            base = base.where(RuleEvaluationResult.category == category)
        if severity:
            base = base.where(RuleEvaluationResult.severity == severity)

        total = (await self.db.execute(
            select(func.count()).select_from(base.subquery())
        )).scalar_one()

        rows = (await self.db.execute(
            base.order_by(
                RuleEvaluationResult.rule_id,
                RuleEvaluationResult.evaluated_at,
            )
            .offset(offset)
            .limit(limit)
        )).scalars().all()
        return list(rows), int(total or 0)

    async def get_failed_pages_for_rule(
        self,
        audit_id: UUID,
        rule_id: str,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> Tuple[List[RuleEvaluationResult], int]:
        """Paginated failed pages for a single rule — used by /issues/{id}/pages."""
        base = select(RuleEvaluationResult).where(
            RuleEvaluationResult.audit_id == audit_id,
            RuleEvaluationResult.rule_id == rule_id,
            RuleEvaluationResult.passed == False,  # noqa: E712
        )
        total = (await self.db.execute(
            select(func.count()).select_from(base.subquery())
        )).scalar_one()
        rows = (await self.db.execute(
            base.order_by(RuleEvaluationResult.evaluated_at)
            .offset(offset)
            .limit(limit)
        )).scalars().all()
        return list(rows), int(total or 0)

    async def get_first_samples_for_rule(
        self,
        audit_id: UUID,
        rule_id: str,
        n: int,
    ) -> List[RuleEvaluationResult]:
        """First N failed rows for a rule — used for sample[0..2] and evidence details."""
        rows = (await self.db.execute(
            select(RuleEvaluationResult).where(
                RuleEvaluationResult.audit_id == audit_id,
                RuleEvaluationResult.rule_id == rule_id,
                RuleEvaluationResult.passed == False,  # noqa: E712
            )
            .order_by(RuleEvaluationResult.evaluated_at)
            .limit(n)
        )).scalars().all()
        return list(rows)

    async def get_failed_for_page(
        self,
        audit_id: UUID,
        page_id: UUID,
    ) -> List[RuleEvaluationResult]:
        """All failed rule results for one (audit, page) — for /pages/{id}."""
        rows = (await self.db.execute(
            select(RuleEvaluationResult).where(
                RuleEvaluationResult.audit_id == audit_id,
                RuleEvaluationResult.page_id == page_id,
                RuleEvaluationResult.passed == False,  # noqa: E712
            )
        )).scalars().all()
        return list(rows)

    async def get_summary(self, audit_id: UUID) -> Dict[str, Any]:
        """Get aggregate counts for an audit."""
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
            ).where(RuleEvaluationResult.audit_id == audit_id)
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

    async def delete_by_audit_id(self, audit_id: UUID) -> int:
        """Delete all rule results for an audit. Returns count deleted."""
        result = await self.db.execute(
            delete(RuleEvaluationResult).where(
                RuleEvaluationResult.audit_id == audit_id
            )
        )
        return result.rowcount
