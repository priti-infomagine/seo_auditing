from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.models.seo_analysis_runs import SeoAnalysisRun
from app.modules.crawler.models.crawl_jobs import CrawlJob
from app.modules.crawler.repositories.crawl_job_repository import CrawlJobRepository


class AuthorizationService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.crawl_job_repo = CrawlJobRepository(db)

    async def validate_project_access(self, project_id: UUID, user_id: UUID) -> CrawlJob:
        crawl_job = await self.crawl_job_repo.get_by_project_id(project_id)
        if crawl_job is None:
            raise ValueError("Project not found")
        if crawl_job.user_id != user_id:
            raise PermissionError("Not authorized to access this project")
        return crawl_job
