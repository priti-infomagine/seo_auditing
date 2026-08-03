"""
POST /audit/run — Mock combined crawler + parser audit.

Takes a URL as input and simulates the full crawl → parse pipeline.
This is a MOCK endpoint that does not perform real crawling or parsing,
nor does it store any data. It provides a blueprint for the future
real implementation.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.logger import logger
from app.schemas.audit_schemas import AuditRequest, AuditResponse
from app.services.audit_service import MockAuditService

router = APIRouter()


@router.post(
    "/run",
    response_model=AuditResponse,
    status_code=200,
    summary="Run mock combined crawl + parse audit",
    description="MOCK endpoint: Simulates the full crawl + parse pipeline for a website without performing real operations or storing data",
)
async def run_audit(
    body: AuditRequest,
    db: AsyncSession = Depends(get_db),
) -> AuditResponse:
    """
    Run a mock combined crawl + parse audit.

    Args:
        body: AuditRequest containing URL to audit
        db: Database session (required by architecture, though not used)

    Returns:
        AuditResponse with mock crawl and parse results

    Raises:
        HTTPException: If the audit fails
    """
    logger.info(f"POST /audit/run - Mock audit endpoint called for URL: {body.url}")

    try:
        # Initialize mock audit service
        service = MockAuditService()

        # Run mock audit
        result = service.audit_website(body.url, deep_crawl=body.deep_crawl)

        logger.info(f"Mock audit successful for URL: {body.url}")

        return AuditResponse(
            success=True,
            message=result["message"],
            url=result["url"],
            domain=result["domain"],
            crawl=result["crawl"],
            parse=result["parse"],
            mock=True,
        )

    except ValueError as e:
        logger.warning(f"Invalid URL for audit: {body.url} - {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Unexpected error during mock audit for URL: {body.url}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred during mock audit",
        )