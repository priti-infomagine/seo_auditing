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


def _markdown_report(
    row,
    findings,
    recommendations,
) -> str:
    """Render the robots result in a readable Markdown format."""
    lines = ["### Sitemaps", ""]
    sitemaps = row.sitemaps_declared or []
    if sitemaps:
        lines.extend(f"- {sitemap}" for sitemap in sitemaps)
    else:
        lines.append("- None declared")

    lines.extend(["", "### Crawler rules", ""])
    groups = row.user_agent_groups or []
    if groups:
        for group in groups:
            user_agents = group.get("user_agents") or ["*"]
            label = ", ".join(
                "All crawlers" if user_agent == "*" else user_agent
                for user_agent in user_agents
            )
            lines.append(label)
            for directive in group.get("disallow", []):
                lines.append(f"- Disallow: {directive}")
            for directive in group.get("allow", []):
                lines.append(f"- Allow: {directive}")
            if group.get("crawl_delay") is not None:
                lines.append(f"- Crawl-delay: {group['crawl_delay']}")
            lines.append("")
    else:
        lines.append("- No crawler rules parsed")

    lines.extend([
        "### Raw robots.txt",
        "",
        "```",
        row.raw_content or "",
        "```",
        "",
        "### Recommendations and fixes",
        "",
    ])
    for item in recommendations:
        lines.append(f"#### `{item.code}`")
        lines.append(f"- Fix: {item.recommendation}")
        if item.evidence:
            lines.append(f"- Evidence: {item.evidence}")
        lines.append("")

    if not recommendations:
        lines.append("- No recommendations. The robots.txt checks passed.")

    return "\n".join(lines).rstrip()


def _to_response(row) -> RobotsCheckResponse:
    from .ai_insight import recommendation_for_code
    from .schema import RobotsFinding, RobotsRecommendation
    findings = []
    raw_findings = getattr(row, "findings", None) or []
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

    recommendations = []
    for index, finding in enumerate(findings):
        recommendation = (
            row.recommendation
            if index == 0 and row.recommendation
            else recommendation_for_code(finding.code)
        )
        recommendations.append(RobotsRecommendation(
            code=finding.code,
            recommendation=recommendation,
            evidence=finding.evidence,
        ))

    response = RobotsCheckResponse(
        id=row.id,
        domain=row.domain,
        checked_at=row.created_at.isoformat() if row.created_at else None,
        exists=row.exists,
        status_code=row.status_code,
        fetch_status=row.fetch_status.value if hasattr(row.fetch_status, "value") else row.fetch_status,
        fetch_url=row.fetched_url,
        size_bytes=row.size_bytes,
        raw_content=row.raw_content,
        report_markdown="",
        sitemaps_declared=row.sitemaps_declared or [],
        sitemap_reachability=row.sitemap_reachability or [],
        syntax_warnings=row.syntax_warnings or [],
        findings=findings,
        recommendations=recommendations,
        overall_status=row.overall_status.value if hasattr(row.overall_status, "value") else row.overall_status,
        severity=row.severity.value if hasattr(row.severity, "value") else row.severity,
        why=row.why,
        recommendation=row.recommendation,
    )
    response.report_markdown = _markdown_report(row, findings, recommendations)
    return response


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
