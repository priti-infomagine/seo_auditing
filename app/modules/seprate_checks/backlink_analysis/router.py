from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.logger import logger

from .model import BacklinkCheck, BacklinkCheckStatus
from .repository import BacklinkCheckRepository
from .schema import (
    BacklinkEvidence,
    BacklinkCheckListResponse,
    BacklinkCheckRequest,
    BacklinkCheckResponse,
    BacklinkReport,
)
from .service import BacklinkAnalysisService, DataForSEOConfigurationError
from app.modules.seprate_checks.meta_check.validation import normalize_target_url

router = APIRouter()


def _bounded_evidence(value: object) -> BacklinkEvidence:
    if not isinstance(value, dict):
        return BacklinkEvidence()

    return BacklinkEvidence(
        referringPages=[
            url
            for url in value.get("referringPages", [])
            if isinstance(url, str)
        ][:5]
        if isinstance(value.get("referringPages"), list)
        else [],
        brokenBacklinks=[
            url
            for url in value.get("brokenBacklinks", [])
            if isinstance(url, str)
        ][:5]
        if isinstance(value.get("brokenBacklinks"), list)
        else [],
    )


def _stored_report(check: BacklinkCheck) -> BacklinkReport | None:
    result = check.result
    if result is None:
        return None

    try:
        if isinstance(result, list) and len(result) == 1:
            legacy_report = result[0]
            if isinstance(legacy_report, dict) and isinstance(
                legacy_report.get("data"), dict
            ):
                data = legacy_report["data"]
                return BacklinkReport(
                    domain=data.get("domain") or data.get("target") or check.target,
                    domainRank=data.get("domainRank", data.get("rank")),
                    backlinks=data.get("backlinks"),
                    referringDomains=data.get("referringDomains"),
                    referringPages=data.get("referringPages"),
                    brokenBacklinks=data.get("brokenBacklinks"),
                    cost=legacy_report.get("cost", check.cost),
                    evidence=_bounded_evidence(legacy_report.get("evidence")),
                )

        if isinstance(result, dict):
            normalized = dict(result)
            normalized["domain"] = normalized.get("domain") or check.target
            normalized["evidence"] = _bounded_evidence(
                normalized.get("evidence")
            )
            return BacklinkReport(**normalized)
    except ValidationError:
        logger.error("Backlink check %s has invalid stored report fields", check.id)
        return None

    logger.error(
        "Backlink check %s has unsupported stored report format",
        check.id,
    )
    return None


def _to_response(check: BacklinkCheck) -> BacklinkCheckResponse:
    report = _stored_report(check)
    error = check.error
    if check.result is not None and report is None:
        error = error or "Stored backlink result has an unsupported format"

    return BacklinkCheckResponse(
        check_id=check.id,
        target=check.target,
        status=BacklinkCheckStatus(check.status),
        result=report,
        cost=check.cost,
        error=error,
        created_at=check.created_at.isoformat() if check.created_at else None,
        updated_at=check.updated_at.isoformat() if check.updated_at else None,
    )


async def _get_check(check_id: str, db: AsyncSession) -> BacklinkCheck:
    try:
        parsed_id = UUID(check_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid check ID format (must be a valid UUID)",
        ) from exc

    check = await BacklinkCheckRepository(db).get(parsed_id)
    if check is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Backlink check with ID '{check_id}' not found",
        )
    return check


@router.post(
    "/check",
    response_model=BacklinkReport,
    status_code=status.HTTP_200_OK,
    summary="Run and save a backlink analysis",
)
async def check_backlinks(
    body: BacklinkCheckRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> BacklinkReport:
    try:
        check = await BacklinkAnalysisService.run_check(
            body.target,
            db,
        )
        response.headers["Location"] = f"/api/v1/backlinks/checks/{check.id}"
        if check.result is None:
            raise RuntimeError("Backlink analysis completed without a result")
        return BacklinkReport(**check.result)
    except DataForSEOConfigurationError as exc:
        logger.error("check_backlinks: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Backlink analysis provider is not configured",
        ) from exc
    except (httpx.HTTPError, RuntimeError, ValueError) as exc:
        logger.error("check_backlinks: DataForSEO request failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Backlink analysis provider request failed",
        ) from exc


@router.get(
    "/checks",
    response_model=BacklinkCheckListResponse,
    summary="List saved backlink analyses",
)
async def list_backlink_checks(
    target: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> BacklinkCheckListResponse:
    normalized_target = None
    if target is not None:
        try:
            _, normalized_target = normalize_target_url(target)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            ) from exc
    checks, total = await BacklinkCheckRepository(db).list(
        normalized_target,
        limit,
        offset,
    )
    return BacklinkCheckListResponse(
        items=[_to_response(check) for check in checks],
        total=total,
    )


@router.get(
    "/checks/{check_id}",
    response_model=BacklinkCheckResponse,
    summary="Retrieve a saved backlink analysis",
)
async def get_backlink_check(
    check_id: str,
    db: AsyncSession = Depends(get_db),
) -> BacklinkCheckResponse:
    check = await _get_check(check_id, db)
    return _to_response(check)
