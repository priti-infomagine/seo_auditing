"""
POST /parser/parse — Parse the latest crawled data for a website.

Takes a website/domain name as input, matches it with the latest crawled .json file,
parses the data using the parser service, and saves the output to storage/parsed/{domain}/
with incremental test number.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.logger import logger
from app.modules.parser.schemas.parser_schema import ParseRequest, ParseResponse
from app.modules.parser.services.pseud_parse_service import ParseService

router = APIRouter()


@router.post(
    "/parse",
    response_model=ParseResponse,
    status_code=200,
    summary="Parse the latest crawled data for a website",
    description="Matches the provided website with the latest crawled .json file, parses it, and saves the output to storage/parsed/{domain}/ with incremental test number",
)
async def parse_website(
    body: ParseRequest,
    db: AsyncSession = Depends(get_db),
) -> ParseResponse:
    """
    Parse the latest crawled data for a website.

    Args:
        body: ParseRequest containing website name to parse
        db: Database session (required by architecture, though not used for parse storage)

    Returns:
        ParseResponse with parse results and file path

    Raises:
        HTTPException: If no crawl data found or parsing fails
    """
    logger.info(f"POST /parser/parse - Parse endpoint called for website: {body.website}")

    try:
        # Initialize parse service
        service = ParseService()

        # Perform parsing
        result = service.parse_website(body.website)

        logger.info(f"Parse successful for website: {body.website}")

        return ParseResponse(
            success=True,
            message="Parsing completed successfully",
            website=result["website"],
            test_number=result["test_number"],
            file_path=result["file_path"],
            parsed_at=result["parsed_at"],
            source_crawl_file=result["source_crawl_file"],
            data=result.get("data"),
        )

    except ValueError as e:
        # No crawl data found or invalid website
        logger.warning(f"No crawl data for website: {body.website} - {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except RuntimeError as e:
        # Parsing failed
        logger.error(f"Parse failed for website: {body.website} - {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Parsing failed: {str(e)}",
        )
    except Exception as e:
        # Unexpected error
        logger.error(f"Unexpected error during parse for website: {body.website}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred during parsing",
        )