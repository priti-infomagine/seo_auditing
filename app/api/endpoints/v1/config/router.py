"""
Config routes — URL ignore pattern management and skip records.

Endpoints:
- GET    /config/ignore-patterns              — List all active patterns
- POST   /config/ignore-patterns              — Create a new pattern
- GET    /config/ignore-patterns/{id}         — Get a single pattern
- PUT    /config/ignore-patterns/{id}         — Update a pattern
- DELETE /config/ignore-patterns/{id}         — Deactivate (soft-delete) a pattern
- PATCH  /config/ignore-patterns/{id}/disable  — Deactivate a pattern
- GET    /config/ignore-patterns/scope/{scope} — List patterns by scope
- GET    /config/ignore-patterns/breakdown/{audit_id} — Skip breakdown for an audit
- GET    /config/ignore-patterns/skips/{audit_id} — Detailed skip records for an audit
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from typing import List
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.crawler.services.url_ignore_service import _VALID_SCOPES
from app.modules.config.repositories.url_ignore_repository import UrlIgnorePatternRepository
from app.modules.config.schemas import (
    UrlIgnorePatternCreate,
    UrlIgnorePatternUpdate,
    UrlIgnorePatternResponse,
    UrlIgnoreSkipRecordResponse,
    UrlIgnoreSkipListResponse,
    SkipBreakdownResponse,
)

router = APIRouter()


@router.get(
    "/",
    response_model=List[UrlIgnorePatternResponse],
    summary="List all URL ignore patterns",
    description="Returns all active URL ignore patterns across all scopes",
)
async def list_ignore_patterns(
    db: AsyncSession = Depends(get_db),
):
    repo = UrlIgnorePatternRepository(db)
    patterns = await repo.get_all_active_patterns()
    return [UrlIgnorePatternResponse.model_validate(p) for p in patterns]


@router.post(
    "/",
    response_model=UrlIgnorePatternResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new URL ignore pattern",
    description="Create a new URL ignore pattern for a specific scope (global, performance, accessibility, bestpractices, seo)",
)
async def create_ignore_pattern(
    payload: UrlIgnorePatternCreate,
    db: AsyncSession = Depends(get_db),
):
    repo = UrlIgnorePatternRepository(db)
    pattern = await repo.create(payload.model_dump())
    return UrlIgnorePatternResponse.model_validate(pattern)


@router.get(
    "/{pattern_id}",
    response_model=UrlIgnorePatternResponse,
    summary="Get a single URL ignore pattern",
)
async def get_ignore_pattern(
    pattern_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    repo = UrlIgnorePatternRepository(db)
    pattern = await repo.get_by_id(pattern_id)
    if not pattern:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="URL ignore pattern not found",
        )
    return UrlIgnorePatternResponse.model_validate(pattern)


@router.put(
    "/{pattern_id}",
    response_model=UrlIgnorePatternResponse,
    summary="Update a URL ignore pattern",
)
async def update_ignore_pattern(
    pattern_id: UUID,
    payload: UrlIgnorePatternUpdate,
    db: AsyncSession = Depends(get_db),
):
    repo = UrlIgnorePatternRepository(db)
    pattern = await repo.get_by_id(pattern_id)
    if not pattern:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="URL ignore pattern not found",
        )
    updated = await repo.update(pattern, payload.model_dump(exclude_unset=True))
    return UrlIgnorePatternResponse.model_validate(updated)


@router.delete(
    "/{pattern_id}",
    response_model=UrlIgnorePatternResponse,
    summary="Delete (deactivate) a URL ignore pattern",
)
async def delete_ignore_pattern(
    pattern_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    repo = UrlIgnorePatternRepository(db)
    pattern = await repo.get_by_id(pattern_id)
    if not pattern:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="URL ignore pattern not found",
        )
    await repo.deactivate(pattern_id)
    pattern.is_active = False
    return UrlIgnorePatternResponse.model_validate(pattern)


@router.patch(
    "/{pattern_id}/disable",
    response_model=UrlIgnorePatternResponse,
    summary="Disable a URL ignore pattern",
)
async def disable_ignore_pattern(
    pattern_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    repo = UrlIgnorePatternRepository(db)
    pattern = await repo.get_by_id(pattern_id)
    if not pattern:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="URL ignore pattern not found",
        )
    await repo.deactivate(pattern_id)
    pattern.is_active = False
    return UrlIgnorePatternResponse.model_validate(pattern)


@router.get(
    "/scope/{scope}",
    response_model=List[UrlIgnorePatternResponse],
    summary="List URL ignore patterns by scope",
    description="Filter patterns by scope: global|performance|accessibility|bestpractices|seo",
)
async def get_patterns_by_scope(
    scope: str,
    db: AsyncSession = Depends(get_db),
):
    if scope not in _VALID_SCOPES and scope != "runtime":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid scope '{scope}'. Must be one of: global, performance, accessibility, bestpractices, seo",
        )
    repo = UrlIgnorePatternRepository(db)
    patterns = await repo.get_by_scope(scope)
    return [UrlIgnorePatternResponse.model_validate(p) for p in patterns]


@router.get(
    "/breakdown/{audit_id}",
    response_model=SkipBreakdownResponse,
    summary="Get skip breakdown for an audit",
    description="Returns a breakdown of skipped URLs by reason for the given audit_id",
)
async def get_skip_breakdown(
    audit_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    repo = UrlIgnorePatternRepository(db)
    breakdown = await repo.get_skip_breakdown_by_audit(audit_id)
    total = await repo.get_skip_count_by_audit(audit_id)
    return SkipBreakdownResponse(
        audit_id=str(audit_id),
        total_skipped=total,
        by_reason=breakdown,
        by_scope={},
    )


@router.get(
    "/skips/{audit_id}",
    response_model=UrlIgnoreSkipListResponse,
    summary="Get detailed skip records for an audit",
    description="Returns detailed skip records for the given audit_id with pagination",
)
async def get_skip_records(
    audit_id: UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    repo = UrlIgnorePatternRepository(db)
    records, total = await repo.get_skips_by_audit(audit_id, skip=skip, limit=limit)
    return UrlIgnoreSkipListResponse(
        total=total,
        skips=[UrlIgnoreSkipRecordResponse.model_validate(r) for r in records],
    )


__all__ = ["router"]
