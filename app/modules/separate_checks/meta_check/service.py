import time
from typing import Any, Callable, Optional
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory
from app.core.logger import logger
from app.modules.crawler.models.crawl_jobs import CrawlJob
from app.modules.crawler.models.crawl_pages import CrawlPage
from app.modules.crawler.models.page_seo_data import PageSEOData
from app.modules.crawler.services.crawl_orchestrator import CrawlOrchestrator

from .evaluator import evaluate_page, evaluate_site
from .model import MetaCheck, MetaCheckStatus
from .metadata_rows import build_metadata_rows
from .repository import MetaCheckRepository
from .schema import MetaCheckRequest
from .validation import normalize_target_url


class MetaCheckService:
    """Run a multi-page metadata audit through the shared crawler."""

    @classmethod
    async def prepare_check(
        cls, body: MetaCheckRequest, db: AsyncSession
    ) -> MetaCheck:
        canonical_url, domain = normalize_target_url(body.url)
        check_id = uuid4()
        check = MetaCheck(
            id=check_id,
            url=canonical_url,
            domain=domain,
            status=MetaCheckStatus.QUEUED.value,
            progress={
                "phase": "queued",
                "message": "Check queued in worker",
                "respect_robots": body.respect_robots,
            },
            max_pages=body.max_pages,
            max_depth=body.max_depth,
        )
        crawl_job = CrawlJob(
            id=check_id,
            user_id=uuid4(),
            url=canonical_url,
            domain=domain,
            status="queued",
            crawl_type="meta",
            max_pages=body.max_pages,
            max_depth=body.max_depth,
            crawl_config={
                "max_pages": body.max_pages,
                "max_depth": body.max_depth,
                "respect_robots": body.respect_robots,
                "enable_browser_rendering": True,
                "render_fallback_enabled": True,
            },
        )
        db.add(crawl_job)
        await MetaCheckRepository(db).create(check)
        await db.commit()
        return check
        return check

    async def run_check_async(
        self,
        check_id: UUID,
        db: Optional[AsyncSession] = None,
        update_state: Optional[Callable[[str, Optional[dict]], None]] = None,
    ) -> dict[str, Any]:
        start_time = time.perf_counter()
        if db is not None:
            return await self._execute(check_id, db, update_state, start_time)
        async with async_session_factory() as session:
            return await self._execute(check_id, session, update_state, start_time)

    async def _execute(
        self,
        check_id: UUID,
        db: AsyncSession,
        update_state: Optional[Callable[[str, Optional[dict]], None]],
        start_time: float,
    ) -> dict[str, Any]:
        repo = MetaCheckRepository(db)
        check = await repo.get(check_id)
        if check is None:
            raise ValueError(f"MetaCheck with id {check_id} not found")

        try:
            progress = {
                "phase": "crawling",
                "message": f"Crawling up to {check.max_pages} page(s)...",
                "pages_crawled": 0,
                "max_pages": check.max_pages,
                "respect_robots": (check.progress or {}).get("respect_robots", True),
            }
            await repo.update_progress(check_id, MetaCheckStatus.PROCESSING, progress)
            await db.commit()
            if update_state:
                update_state("PROGRESS", progress)

            def on_progress(current: int, total: int | None) -> None:
                payload = {
                    "phase": "crawling",
                    "message": f"Crawled {current} page(s)",
                    "pages_crawled": current,
                    "max_pages": total or check.max_pages,
                }
                if update_state:
                    update_state("PROGRESS", payload)

            orchestrator = CrawlOrchestrator(db, check_id)
            await orchestrator.run(
                start_url=check.url,
                max_depth=check.max_depth,
                max_pages=check.max_pages,
                respect_robots=(check.progress or {}).get("respect_robots", True),
                progress_callback=on_progress,
            )

            page_rows = (
                await db.execute(
                    select(CrawlPage)
                    .where(CrawlPage.audit_id == check_id)
                    .order_by(CrawlPage.depth, CrawlPage.url)
                )
            ).scalars().all()
            seo_rows = (
                await db.execute(
                    select(PageSEOData).where(
                        PageSEOData.page_id.in_([page.id for page in page_rows])
                    )
                )
            ).scalars().all()
            seo_by_page = {row.page_id: row for row in seo_rows}

            pages: list[dict[str, Any]] = []
            for page in page_rows:
                seo = seo_by_page.get(page.id)
                item = {
                    "url": page.url,
                    "status_code": page.status_code,
                    "final_url": page.final_url,
                    "content_type": page.content_type,
                    "title": seo.title if seo else "",
                    "title_length": seo.title_length if seo else 0,
                    "meta_description": seo.meta_description if seo else "",
                    "meta_description_length": seo.meta_description_length if seo else 0,
                    "page_metadata": seo.page_metadata if seo else {},
                    "error": None if page.is_success else "Page crawl failed",
                }
                item["metadata"] = build_metadata_rows(item)
                item["findings"] = evaluate_page(item)
                pages.append(item)

            findings, summary, overall_status, severity = evaluate_site(pages)
            cost_seconds = round(time.perf_counter() - start_time, 3)
            await repo.update_completed(
                check_id=check_id,
                pages=pages,
                findings=findings,
                summary=summary,
                overall_status=overall_status,
                severity=severity,
                cost_seconds=cost_seconds,
            )
            await db.commit()
            return {
                "status": MetaCheckStatus.COMPLETED.value,
                "check_id": str(check_id),
                "pages_checked": summary["pages_checked"],
                "total_findings": summary["total_findings"],
            }
        except Exception as exc:
            logger.error("Meta check failed for %s: %s", check_id, exc, exc_info=True)
            await db.rollback()
            await repo.update_progress(
                check_id,
                MetaCheckStatus.FAILED,
                progress={"phase": "failed", "message": "Metadata crawl failed"},
                error=str(exc)[:1024],
            )
            await db.commit()
            raise