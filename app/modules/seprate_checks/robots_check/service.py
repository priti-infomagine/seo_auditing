"""
Robots check service — orchestrates fetch → parse → evaluate → AI insight → persist.

All methods are ``async def``. No Celery. A single ``POST /check`` completes
the full flow within the request lifecycle (or short-circuits on a fresh cache).
"""
import asyncio
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import AsyncGenerator, Optional

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory
from app.core.datetime_utils import utc_now
from app.core.logger import logger

from . import parser as parser_module
from .evaluator import evaluate
from .fetcher import fetch_robots_txt, FetchResult, FetchStatus, ParsedRobots
from .ai_insight import generate_insights
from .repository import RobotCheckRepository
from .model import OverallStatus, Severity, RobotCheck
from .validation import validate_domain

CACHE_TTL_HOURS = 24
VERSION = "1.0.0"

SAITEMAP_CHECK_TIMEOUT = 10.0
SITEMAP_CONCURRENCY = 5


class RobotsCheckService:
    """Orchestrates the full robots.txt check flow."""

    VERSION = VERSION

    def __init__(self, db: Optional[AsyncSession] = None):
        self._db = db

    async def run_check(
        self,
        domain: str,
        force: bool = False,
    ) -> RobotCheck:
        """Run a full robots.txt check for *domain*.

        Returns a stored :class:`RobotCheck` row. If a fresh cached row
        exists (within ``CACHE_TTL_HOURS``) it is returned without re-fetching,
        unless *force* is ``True``.
        """
        normalized_domain = validate_domain(domain)

        # 1. Cache check
        if not force:
            cached = await self.get_latest(normalized_domain)
            if cached is not None:
                age = utc_now() - cached.created_at
                if age < timedelta(hours=CACHE_TTL_HOURS):
                    logger.info(
                        "RobotsCheckService: cache hit for %s (age=%.1fh)",
                        normalized_domain,
                        age.total_seconds() / 3600,
                    )
                    return cached

        # 2. Fetch (HTTPS → HTTP fallback)
        try:
            fetch_result = await fetch_robots_txt(normalized_domain)
        except Exception as exc:
            logger.error(
                "RobotsCheckService: fetch failed for %s: %s",
                normalized_domain,
                exc,
            )
            fetch_result = FetchResult(
                url=f"https://{normalized_domain}/robots.txt",
                text="",
                status_code=0,
                response_time_ms=0,
                final_url="",
                content_length=0,
                error=str(exc),
                success=False,
                fetch_status=FetchStatus.UNREACHABLE,
            )

        # 3. Parse (graceful degradation)
        parsed: Optional[ParsedRobots] = None
        if fetch_result.text:
            try:
                parsed = parser_module.parse_robots_txt(fetch_result.text)
            except Exception as exc:
                logger.warning(
                    "RobotsCheckService: parse failed for %s: %s",
                    normalized_domain,
                    exc,
                )
                parsed = ParsedRobots(
                    user_agent_groups=[],
                    sitemaps=[],
                    crawl_delay=None,
                    syntax_warnings=[f"Parse error: {exc}"],
                    raw_text=fetch_result.text,
                )

        # 4. Check sitemap reachability concurrently
        sitemap_reachability: list[dict] = []
        if parsed and parsed.sitemaps:
            sitemap_reachability = await self._check_sitemaps_concurrent(
                parsed.sitemaps
            )

        # 5. Evaluate
        evaluation = evaluate(parsed, fetch_result, sitemap_reachability)

        # 6. AI insights (graceful degradation)
        try:
            insights = await generate_insights(evaluation, fetch_result, parsed)
        except Exception as exc:
            logger.warning(
                "RobotsCheckService: AI insights failed: %s", exc
            )
            insights = {}

        # 7. Store
        row = RobotCheck(
            domain=normalized_domain,
            exists=fetch_result.fetch_status == FetchStatus.SUCCESS,
            status_code=fetch_result.status_code,
            fetch_status=fetch_result.fetch_status,
            size_bytes=fetch_result.content_length,
            raw_content=fetch_result.text if fetch_result.text else None,
            fetched_url=fetch_result.final_url if fetch_result.final_url else None,
            user_agent_groups=parsed.user_agent_groups if parsed else [],
            sitemaps_declared=parsed.sitemaps if parsed else [],
            sitemap_reachability=sitemap_reachability,
            syntax_warnings=parsed.syntax_warnings if parsed else [],
            findings=evaluation.findings,
            blocks_entire_site=evaluation.blocks_entire_site,
            blocks_assets=evaluation.blocks_assets,
            oversized=evaluation.oversized,
            overall_status=OverallStatus(evaluation.overall_status),
            severity=Severity(evaluation.severity),
            evidence=evaluation.evidence_str,
            why=insights.get("why"),
            recommendation=insights.get("recommendation"),
            check_version=self.VERSION,
        )

        async with self._session_ctx() as db:
            repo = RobotCheckRepository(db)
            await repo.create(row)
            await db.commit()
            await db.refresh(row)
            return row

    async def get_latest(self, domain: str) -> Optional[RobotCheck]:
        """Return the most recent :class:`RobotCheck` for *domain* (no HTTP)."""
        normalized_domain = validate_domain(domain)
        async with self._session_ctx() as db:
            repo = RobotCheckRepository(db)
            return await repo.get_latest_by_domain(normalized_domain)

    async def _check_sitemaps_concurrent(
        self, sitemap_urls: list[str]
    ) -> list[dict]:
        """Check all sitemap URLs concurrently via HEAD requests."""
        sem = asyncio.Semaphore(SITEMAP_CONCURRENCY)

        async def _check_one(url: str) -> dict:
            async with sem:
                try:
                    async with httpx.AsyncClient(
                        timeout=SAITEMAP_CHECK_TIMEOUT,
                        follow_redirects=True,
                    ) as client:
                        resp = await client.head(url)
                        return {
                            "url": url,
                            "status_code": resp.status_code,
                            "reachable": 200 <= resp.status_code < 400,
                            "error": None,
                        }
                except Exception as exc:
                    return {
                        "url": url,
                        "status_code": 0,
                        "reachable": False,
                        "error": str(exc),
                    }

        return await asyncio.gather(*[_check_one(u) for u in sitemap_urls])

    @asynccontextmanager
    async def _session_ctx(self) -> AsyncGenerator[AsyncSession, None]:
        """Yield an async session, using injected db if available."""
        if self._db is not None:
            yield self._db
        else:
            async with async_session_factory() as session:
                yield session
