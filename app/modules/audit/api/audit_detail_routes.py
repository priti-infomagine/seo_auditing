"""
Compact audit detail routes — additive read layer.

These endpoints are mounted under ``/api/v1/audits/...`` (note the trailing
``s`` — distinct from the legacy ``/api/v1/audit/...`` namespace) to make
the new contract visually separate. Existing ``/audit/...`` endpoints are
untouched and continue to return the full ``UnifiedAuditResponse`` shape.

All routes are read-only and backed by ``AuditReadModelService``. They
do not perform any crawl, parse, evaluate, score, or LLM work.

Cache keys (not implemented in this PR — see plan §11):
    audit:overview:{audit_id}
    audit:issues:{audit_id}:...
    audit:issue:{audit_id}:{issue_id}
    audit:issue_pages:{audit_id}:{issue_id}:...
    audit:issue_evidence:{audit_id}:{issue_id}
    audit:page:{audit_id}:{page_id}
"""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.audit.schemas.audit_summary_schemas import AuditOverview
from app.modules.audit.schemas.issue_detail_schemas import (
    IssueDetailResponse,
    IssueEvidenceResponse,
    IssueListResponse,
    IssuePagesResponse,
    PageDetailResponse,
)
from app.modules.audit.services.audit_read_model_service import AuditReadModelService

router = APIRouter()

# router.include_router()

def _not_found(audit_id: UUID) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"No completed analysis found for audit_id={audit_id}",
    )


@router.get(
    "/{audit_id}/overview",
    response_model=AuditOverview,
    summary="Compact audit overview (additive read layer)",
    description=(
        "Returns a small, dashboard-friendly projection of the audit: "
        "metadata, score, per-tier issue counts, per-category aggregates, "
        "and up to 10 top issues (each with up to 3 sample pages). "
        "Per-page facts, evidence, and full affected-page lists are NOT "
        "included — fetch them from the lazy endpoints below."
    ),
)
async def get_audit_overview(
    audit_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> AuditOverview:
    service = AuditReadModelService(db)
    try:
        return await service.build_overview(audit_id)
    except LookupError:
        raise _not_found(audit_id)


@router.get(
    "/{audit_id}/issues",
    response_model=IssueListResponse,
    summary="Paginated compact issue list",
    description=(
        "Returns compact summaries of failed rules for the audit. "
        "Filters: category, severity, status (failed|passed). "
        "Pagination uses limit/offset (matches existing endpoints)."
    ),
)
async def list_audit_issues(
    audit_id: UUID,
    category: Optional[str] = Query(None, description="Filter by category id"),
    severity: Optional[str] = Query(
        None, description="Filter by severity (critical|high|medium|low)"
    ),
    status: Optional[str] = Query(
        None, description="Filter by status (failed|passed); defaults to failed"
    ),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> IssueListResponse:
    service = AuditReadModelService(db)
    try:
        return await service.build_issue_list(
            audit_id,
            category=category,
            severity=severity,
            status=status,
            limit=limit,
            offset=offset,
        )
    except LookupError:
        raise _not_found(audit_id)


@router.get(
    "/{audit_id}/issues/{issue_id}",
    response_model=IssueDetailResponse,
    summary="Issue detail (rule metadata + first 3 examples)",
)
async def get_audit_issue_detail(
    audit_id: UUID,
    issue_id: str,
    db: AsyncSession = Depends(get_db),
) -> IssueDetailResponse:
    service = AuditReadModelService(db)
    try:
        return await service.build_issue_detail(audit_id, issue_id)
    except LookupError:
        raise _not_found(audit_id)


@router.get(
    "/{audit_id}/issues/{issue_id}/pages",
    response_model=IssuePagesResponse,
    summary="Paginated affected pages for one issue",
)
async def get_audit_issue_pages(
    audit_id: UUID,
    issue_id: str,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> IssuePagesResponse:
    service = AuditReadModelService(db)
    try:
        return await service.build_issue_pages(
            audit_id, issue_id, limit=limit, offset=offset,
        )
    except LookupError:
        raise _not_found(audit_id)


@router.get(
    "/{audit_id}/issues/{issue_id}/evidence",
    response_model=IssueEvidenceResponse,
    summary="Lazy-loaded heavy evidence for one issue (links, images, rule_data)",
    description=(
        "Returns heavy evidence on demand. Links and images are paginated. "
        "This endpoint is NOT used by the overview path."
    ),
)
async def get_audit_issue_evidence(
    audit_id: UUID,
    issue_id: str,
    links_limit: int = Query(25, ge=1, le=100),
    links_offset: int = Query(0, ge=0),
    images_limit: int = Query(25, ge=1, le=100),
    images_offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> IssueEvidenceResponse:
    service = AuditReadModelService(db)
    try:
        return await service.build_issue_evidence(
            audit_id, issue_id,
            links_limit=links_limit, links_offset=links_offset,
            images_limit=images_limit, images_offset=images_offset,
        )
    except LookupError:
        raise _not_found(audit_id)


@router.get(
    "/{audit_id}/pages/{page_id}",
    response_model=PageDetailResponse,
    summary="Per-page breakdown (lazy)",
    description=(
        "Returns the per-page issue list. Pass ``?include_facts=1`` to "
        "include the heavy parsed/SEO/network data — the default keeps the "
        "payload small."
    ),
)
async def get_audit_page_detail(
    audit_id: UUID,
    page_id: UUID,
    include_facts: bool = Query(
        False, description="If true, include parsed/SEO/network facts (heavier payload)"
    ),
    db: AsyncSession = Depends(get_db),
) -> PageDetailResponse:
    service = AuditReadModelService(db)
    try:
        return await service.build_page_detail(
            audit_id, page_id, include_facts=include_facts,
        )
    except LookupError as exc:
        if "Page" in str(exc):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(exc),
            )
        raise _not_found(audit_id)
