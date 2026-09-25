"""Sitemap single-check API routes."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.logger import logger

from .model import SitemapCheck
from .repository import SitemapCheckRepository
from .schema import (
    SitemapCheckAcceptedResponse,
    SitemapCheckRequest,
    SitemapFilePage,
    SitemapFilePageItem,
    SitemapRawResponse,
    SitemapUrlPage,
)
from .service import SitemapCheckService

router = APIRouter()


@router.post(
    "/check",
    response_model=SitemapCheckAcceptedResponse,
    status_code=status.HTTP_200_OK,
    summary="Check all sitemap files for a URL",
    description=(
        "Discovers sitemap files from robots.txt and common sitemap locations, "
        "expands sitemap indexes, returns each sitemap contents, and provides "
        "structured findings and recommendations. This endpoint does not crawl page HTML."
    ),
)
async def check_sitemap(
    body: SitemapCheckRequest,
    db: AsyncSession = Depends(get_db),
) -> SitemapCheckAcceptedResponse:
    try:
        result = await SitemapCheckService().run_check(body.url)
        check = await SitemapCheckRepository(db).create(
            SitemapCheck(
                url=body.url,
                status="completed",
                payload=result.model_dump(mode="json"),
            )
        )
        await db.commit()
        return SitemapCheckAcceptedResponse(
            check_id=check.id,
            checked_url=result.checked_url,
            status="completed",
            summary=result.summary,
            robots=result.robots,
            findings=result.findings,
            recommendation_items=result.recommendation_items,
            files_url=f"/api/v1/sitemap/{check.id}/files",
        )
    except ValueError as exc:
        logger.warning("check_sitemap: validation error: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc))
    except TimeoutError as exc:
        logger.warning("check_sitemap: discovery timed out: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=(
                "Sitemap discovery took too long. The site may have too many "
                "sitemap files or an unresponsive sitemap endpoint."
            ),
        )
    except Exception as exc:
        logger.error("check_sitemap: unexpected error: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred while checking sitemaps",
        )


async def _load_check(check_id: str, db: AsyncSession) -> SitemapCheck:
    try:
        parsed_id = UUID(check_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid sitemap check ID") from exc
    check = await SitemapCheckRepository(db).get(parsed_id)
    if check is None:
        raise HTTPException(status_code=404, detail="Sitemap check not found")
    return check


@router.get(
    "/{check_id}/files",
    response_model=SitemapFilePage,
    summary="List sitemap files for a check",
)
async def list_sitemap_files(
    check_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> SitemapFilePage:
    check = await _load_check(check_id, db)
    files = (check.payload or {}).get("sitemap_files", [])
    start = (page - 1) * page_size
    selected = files[start:start + page_size]
    items = [
        SitemapFilePageItem(
            index=start + index,
            url=item.get("url", ""),
            kind=item.get("kind", "urlset"),
            health=item.get("health", "unknown"),
            status_code=item.get("status_code"),
            content_type=item.get("content_type"),
            content_length=item.get("content_length", 0),
            url_count=item.get("url_count", 0),
            child_sitemap_count=len(item.get("child_sitemaps", [])),
            issues=item.get("issues", []),
            error=item.get("error"),
        )
        for index, item in enumerate(selected)
    ]
    return SitemapFilePage(
        items=items,
        page=page,
        page_size=page_size,
        total=len(files),
        has_next=start + page_size < len(files),
    )


@router.get(
    "/{check_id}/files/{file_index}/urls",
    response_model=SitemapUrlPage,
    summary="List URLs from one sitemap file",
)
async def list_sitemap_urls(
    check_id: str,
    file_index: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
) -> SitemapUrlPage:
    check = await _load_check(check_id, db)
    files = (check.payload or {}).get("sitemap_files", [])
    if file_index < 0 or file_index >= len(files):
        raise HTTPException(status_code=404, detail="Sitemap file not found")
    file_data = files[file_index]
    urls = file_data.get("urls", [])
    start = (page - 1) * page_size
    return SitemapUrlPage(
        sitemap_url=file_data.get("url", ""),
        items=urls[start:start + page_size],
        page=page,
        page_size=page_size,
        total=len(urls),
        has_next=start + page_size < len(urls),
    )


@router.get(
    "/{check_id}/files/{file_index}/raw",
    response_model=SitemapRawResponse,
    summary="Get raw XML for one sitemap file",
)
async def get_sitemap_raw(
    check_id: str,
    file_index: int,
    db: AsyncSession = Depends(get_db),
) -> SitemapRawResponse:
    check = await _load_check(check_id, db)
    files = (check.payload or {}).get("sitemap_files", [])
    if file_index < 0 or file_index >= len(files):
        raise HTTPException(status_code=404, detail="Sitemap file not found")
    file_data = files[file_index]
    return SitemapRawResponse(
        sitemap_url=file_data.get("url", ""),
        content_type=file_data.get("content_type"),
        content_length=file_data.get("content_length", 0),
        raw_content=file_data.get("raw_content"),
    )
