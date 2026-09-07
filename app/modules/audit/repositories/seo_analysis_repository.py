"""
SeoAnalysisRun repository - database operations for SeoAnalysisRun model.

Provides upsert for idempotency, ensuring one analysis run per project_id.
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
        Insert or update a SeoAnalysisRun for (project_id).
        Uses one-row-per-project semantics: checks for existing, updates if found.
        """
        existing = await self.get_by_project_id(run.project_id)
        if existing:
            existing.crawl_id = run.crawl_id
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

    async def get_by_project_id(self, project_id: UUID) -> Optional[SeoAnalysisRun]:
        """Get analysis run by project ID."""
        result = await self.db.execute(
            select(SeoAnalysisRun).where(
                SeoAnalysisRun.project_id == project_id
            )
        )
        return result.scalar_one_or_none()

    async def get_by_crawl_id(self, crawl_id: UUID) -> Optional[SeoAnalysisRun]:
        """Get the most recent analysis run for a crawl — additive lookup.

        Used by the new compact read layer to resolve ``audit_id`` (== crawl_id)
        to a (project_id, completed) pair. Returns the latest if multiple exist.
        """
        result = await self.db.execute(
            select(SeoAnalysisRun).where(
                SeoAnalysisRun.crawl_id == crawl_id
            ).order_by(SeoAnalysisRun.scored_at.desc()).limit(1)
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
        """Get all analysis runs for a domain, filtered to a user's project IDs."""
        result = await self.db.execute(
            select(SeoAnalysisRun).where(
                SeoAnalysisRun.project_id.in_(user_project_ids)
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

    async def exists(self, project_id: UUID) -> bool:
        """Check if an analysis run exists for this project_id."""
        result = await self.db.execute(
            select(SeoAnalysisRun.id).where(
                SeoAnalysisRun.project_id == project_id
            )
        )
        return result.scalar_one_or_none() is not None

    async def delete_by_project_id(self, project_id: UUID) -> bool:
        """Delete analysis run for a project."""
        result = await self.db.execute(
            delete(SeoAnalysisRun).where(
                SeoAnalysisRun.project_id == project_id
            )
        )
        return result.rowcount > 0
