"""
Robots check API routes.

POST /robots/check  — Run a robots.txt check (async/await, 200)

Design notes
------------
* Fully async/await — no Celery. ``POST /check`` completes the full
  fetch→parse→evaluate→store cycle within the request lifecycle and returns
  ``200 OK``. If a fresh cached row exists, it short-circuits.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.logger import logger

from .model import FetchStatus, OverallStatus
from .repository import RobotCheckRepository
from .schema import RobotsCheckRequest, RobotsCheckResponse
from .service import RobotsCheckService

router = APIRouter()


def _to_response(row) -> RobotsCheckResponse:
    from .schema import RobotsFinding
    findings = []
    raw_findings = row.evidence or []
    if isinstance(raw_findings, list):
        for f in raw_findings:
            if isinstance(f, dict):
                findings.append(RobotsFinding(
                    code=f.get("code", "unknown"),
                    severity=f.get("severity", "none"),
                    status=f.get("status", "pass"),
                    message=f.get("message", ""),
                    evidence=f.get("evidence"),
                ))
            elif isinstance(f, str):
                findings.append(RobotsFinding(
                    code=f,
                    severity="none",
                    status="pass",
                    message=f,
                    evidence=None,
                ))
    if not findings:
        findings = [RobotsFinding(
            code="robots_ok",
            severity="none",
            status="pass",
            message="No specific findings",
            evidence=row.evidence,
        )]

    return RobotsCheckResponse(
        id=row.id,
        domain=row.domain,
        checked_at=row.created_at.isoformat() if row.created_at else None,
        exists=row.exists,
        status_code=row.status_code,
        fetch_status=row.fetch_status.value if hasattr(row.fetch_status, "value") else row.fetch_status,
        fetch_url=row.fetched_url,
        size_bytes=row.size_bytes,
        sitemaps_declared=row.sitemaps_declared or [],
        sitemap_reachability=row.sitemap_reachability or [],
        syntax_warnings=row.syntax_warnings or [],
        findings=findings,
        overall_status=row.overall_status.value if hasattr(row.overall_status, "value") else row.overall_status,
        severity=row.severity.value if hasattr(row.severity, "value") else row.severity,
        why=row.why,
        recommendation=row.recommendation,
    )


@router.post(
    "/check",
    response_model=RobotsCheckResponse,
    status_code=status.HTTP_200_OK,
    summary="Check robots.txt for a domain",
    description=(
        "Fetches, parses, and evaluates the robots.txt file for the given "
        "domain. Returns 200 with the full result. If a cached result "
        f"checked within the last {RobotsCheckService.VERSION} hour(s) exists, "
        "the cached result is returned without re-fetching."
    ),
)
async def check_robots(
    body: RobotsCheckRequest,
    db: AsyncSession = Depends(get_db),
) -> RobotsCheckResponse:
    service = RobotsCheckService(db)
    try:
        result = await service.run_check(body.domain)
    except ValueError as exc:
        logger.warning("check_robots: validation error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except Exception as exc:
        logger.error("check_robots: unexpected error: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while checking robots.txt",
        )
    return _to_response(result)
