"""
Audit read repository — thin composable wrapper used by the new compact
``AuditReadModelService``.

This module does **not** introduce new SQL on its own. It composes existing
repositories and the additive batch methods added in this PR. It exists so
the service layer can stay small and focused on read-model projection.

The read layer is strictly read-only — no mutation, no write, no caching
write. Caching is intentionally out of scope for this PR (see plan §11).
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.repositories.parsed_page_fact_repository import (
    ParsedPageFactRepository,
)
from app.modules.audit.repositories.rule_evaluation_repository import (
    RuleEvaluationResultRepository,
)
from app.modules.audit.repositories.seo_analysis_repository import (
    SeoAnalysisRunRepository,
)
from app.modules.crawler.repositories.crawl_job_repository import CrawlJobRepository
from app.modules.crawler.repositories.crawl_page_repository import CrawlPageRepository
from app.modules.crawler.repositories.page_seo_data_repository import (
    PageSEODataRepository,
)
from app.modules.crawler.repositories.page_network_data_repository import (
    PageNetworkDataRepository,
)


class AuditReadRepository:
    """Read-only composition over existing audit/crawler repositories.

    The legacy ``AuditResponseBuilder`` also composes these repos but with
    different query patterns. This wrapper exists only to make the new
    compact read path independent and testable.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.analysis_repo = SeoAnalysisRunRepository(db)
        self.crawl_job_repo = CrawlJobRepository(db)
        self.crawl_page_repo = CrawlPageRepository(db)
        self.parsed_fact_repo = ParsedPageFactRepository(db)
        self.rule_eval_repo = RuleEvaluationResultRepository(db)
        self.seo_repo = PageSEODataRepository(db)
        self.network_repo = PageNetworkDataRepository(db)

    async def resolve_audit(
        self, audit_id: UUID
    ) -> Tuple[Optional[UUID], Optional[UUID]]:
        """Resolve ``audit_id`` (== crawl_id) → (project_id, crawl_id).

        Returns ``(None, None)`` if no completed analysis run exists for the
        crawl. We deliberately do not return the run row here — the service
        layer fetches it once to extract scalar summary fields.
        """
        run = await self.analysis_repo.get_by_crawl_id(audit_id)
        if run is None:
            return None, None
        return run.project_id, run.crawl_id

    async def load_compact_inputs(
        self,
        audit_id: UUID,
    ) -> Optional[Dict[str, object]]:
        """Load the constant-size inputs needed to build the compact overview.

        Returns ``None`` if no analysis run exists for the given crawl.
        Performs at most 4 queries:

        1. ``seo_analysis_repo.get_by_crawl_id`` (analysis run row)
        2. ``crawl_job_repo.get_by_id`` (crawl metadata)
        3. ``crawl_page_repo.get_by_crawl_id`` (all crawl pages)
        4. ``rule_eval_repo.get_failed_by_crawl_id`` (failed rules only)

        No per-page ``page_seo_data`` or ``page_network_data`` is loaded —
        those are only fetched lazily by the detail endpoints.
        """
        run = await self.analysis_repo.get_by_crawl_id(audit_id)
        if run is None:
            return None

        crawl_job = await self.crawl_job_repo.get_by_id(run.crawl_id)
        crawl_pages = await self.crawl_page_repo.get_by_crawl_id(run.crawl_id)
        failed_results = await self.rule_eval_repo.get_failed_by_crawl_id(
            run.project_id, run.crawl_id
        )

        return {
            "analysis_run": run,
            "crawl_job": crawl_job,
            "crawl_pages": crawl_pages,
            "failed_results": failed_results,
        }
