"""
Lighthouse check API routes.

POST /lighthouse/check              — Trigger a full Lighthouse check
                                      (crawl → discover URLs → Pagespeed API → persist)
GET  /lighthouse/results/{check_id} — Retrieve stored results by check_id
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.logger import logger
from app.modules.seprate_checks.google_lighthouse_check.model import (
    Device,
    LighthousePageResult,
    PageStatus,
)
from app.modules.seprate_checks.google_lighthouse_check.repository import (
    LighthousePageResultRepository,
)
from app.modules.seprate_checks.google_lighthouse_check.schema import (
    LighthouseCheckRequest,
    LighthouseCheckResponse,
)
from app.modules.seprate_checks.google_lighthouse_check.services import (
    LighthouseCheckService,
)

router = APIRouter()


@router.post(
    "/check",
    response_model=dict,
    status_code=status.HTTP_200_OK,
    summary="Run Google Lighthouse/Pagespeed check",
    description=(
        "Crawls the given URL using the existing crawler module to discover "
        "[performance, seo, best-practices, accessibility] "
        "Lighthouse checks."
    ),
)
async def run_lighthouse_check(
    body: LighthouseCheckRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    1. Creates a CrawlJob
    2. Runs CrawlOrchestrator (sitemap discovery + BFS crawl)
    3. Collects all crawled page URLs from CrawlPageRepository
    4. Calls Google PageSpeed Insights API per URL
    5. Persists LighthousePageResult rows
    """
    logger.info(
        f"POST /lighthouse/check — url={body.url}, device={body.device}, "
        f"max_pages={body.max_pages}"
    )
    try:
        service = LighthouseCheckService()
        result = await service.run_check(
            url=str(body.url),
            device=body.device,
            max_pages=body.max_pages,
        )
        return result
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Lighthouse check failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.get(
    "/results/{check_id}",
    response_model=list[LighthouseCheckResponse],
    summary="Get Lighthouse check results",
    description="Retrieve all Lighthouse page results for a given check_id.",
)
async def get_lighthouse_results(
    check_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get all LighthousePageResult rows for a check_id."""
    try:
        check_uuid = UUID(check_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid check_id format",
        )

    repo = LighthousePageResultRepository(db)
    rows = await repo.get_by_check_id(check_uuid)

    return [
        LighthouseCheckResponse(
            id=r.id,
            url=r.url,
            device=r.device.value if hasattr(r.device, "value") else r.device,
            status=r.status.value if hasattr(r.status, "value") else r.status,
            reason=r.reason,
            performance_score=r.performance_score,
            seo_score=r.seo_score,
            fcp_ms=r.fcp_ms,
            lcp_ms=r.lcp_ms,
            tbt_ms=r.tbt_ms,
            cls=r.cls,
        )
        for r in rows
    ]
