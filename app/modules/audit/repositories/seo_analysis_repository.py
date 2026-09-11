"""
SeoAnalysisRun repository - database operations for SeoAnalysisRun model.

Provides upsert for idempotency, ensuring one analysis run per audit_id.
"""
from typing import List, Optional, Dict, Any
from uuid import UUID

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.models.seo_analysis_runs import SeoAnalysisRun


class SeoAnalysisRunRepository:
    """Repository for SeoAnalysisRun database operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def upsert(self, run: SeoAnalysisRun) -> SeoAnalysisRun:
        """
        Insert or update a SeoAnalysisRun for (audit_id).
        Uses one-row-per-audit semantics: checks for existing, updates if found.
        """
        existing = await self.get_by_audit_id(run.audit_id)
        if existing:
            existing.domain = run.domain
            existing.overall_score = run.overall_score
            existing.grade = run.grade
            existing.total_pages_scored = run.total_pages_scored
            existing.total_rules_evaluated = run.total_rules_evaluated
            existing.total_passed = run.total_passed
            existing.total_failed = run.total_failed
            existing.critical_issues = run.critical_issues
            existing.warnings = run.warnings
            existing.error_pages = run.error_pages
            existing.error_summary = run.error_summary
            existing.category_scores = run.category_scores
            existing.top_issues = run.top_issues
            existing.summary = run.summary
            existing.output_file_path = run.output_file_path
            existing.analysis_status = run.analysis_status
            existing.scored_at = run.scored_at
            self.db.add(existing)
            await self.db.flush()
            await self.db.refresh(existing)
            return existing
        self.db.add(run)
        await self.db.flush()
        await self.db.refresh(run)
        return run

    async def get_by_audit_id(self, audit_id: UUID) -> Optional[SeoAnalysisRun]:
        """Get analysis run by audit ID (== crawl_id)."""
        result = await self.db.execute(
            select(SeoAnalysisRun).where(
                SeoAnalysisRun.audit_id == audit_id
            )
        )
        return result.scalar_one_or_none()

    async def get_by_domain(self, domain: str) -> List[SeoAnalysisRun]:
        """Get all analysis runs for a domain."""
        result = await self.db.execute(
            select(SeoAnalysisRun).where(
                SeoAnalysisRun.domain == domain
            ).order_by(SeoAnalysisRun.scored_at.desc())
        )
        return list(result.scalars().all())

    async def get_latest_by_domain(self, domain: str) -> Optional[SeoAnalysisRun]:
        """Get the most recent analysis run for a domain."""
        result = await self.db.execute(
            select(SeoAnalysisRun).where(
                SeoAnalysisRun.domain == domain
            ).order_by(SeoAnalysisRun.scored_at.desc()).limit(1)
        )
        return result.scalar_one_or_none()

    async def get_by_user_and_domain(self, domain: str, user_project_ids: List[UUID]) -> List[SeoAnalysisRun]:
        """Get all analysis runs for a domain, filtered to a user's audit IDs."""
        result = await self.db.execute(
            select(SeoAnalysisRun).where(
                SeoAnalysisRun.audit_id.in_(user_project_ids)
            ).order_by(SeoAnalysisRun.scored_at.desc())
        )
        return list(result.scalars().all())

    async def get_all(self, limit: int = 100, offset: int = 0) -> List[SeoAnalysisRun]:
        """Get all analysis runs, ordered by scored_at desc."""
        result = await self.db.execute(
            select(SeoAnalysisRun)
            .order_by(SeoAnalysisRun.scored_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def exists(self, audit_id: UUID) -> bool:
        """Check if an analysis run exists for this audit_id."""
        result = await self.db.execute(
            select(SeoAnalysisRun.id).where(
                SeoAnalysisRun.audit_id == audit_id
            )
        )
        return result.scalar_one_or_none() is not None

    async def delete_by_audit_id(self, audit_id: UUID) -> bool:
        """Delete analysis run for an audit."""
        result = await self.db.execute(
            delete(SeoAnalysisRun).where(
                SeoAnalysisRun.audit_id == audit_id
            )
        )
        return result.rowcount > 0
