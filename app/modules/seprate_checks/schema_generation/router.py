from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.logger import logger

from .exceptions import (
    InvalidSchemaTypeError,
    SchemaAuditError,
    SchemaGenerationError,
    ValidationError,
)
from .schema import (
    SchemaAuditRequest,
    SchemaAuditResponse,
    SchemaGenerateRequest,
    SchemaGenerateResponse,
    SchemaTypeInfo,
    SchemaTypesResponse,
)
from .service import SchemaGenerationService

router = APIRouter()


@router.post(
    "/generate",
    response_model=SchemaGenerateResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate JSON-LD schema markup",
    description="Generate valid JSON-LD structured data for SEO. Supports Organization, LocalBusiness, Article (BlogPosting, NewsArticle), and Product schema types.",
)
async def generate_schema(
    body: SchemaGenerateRequest,
    db: AsyncSession = Depends(get_db),
) -> SchemaGenerateResponse:
    try:
        service = SchemaGenerationService(db)
        return await service.generate_schema(body)
    except ValidationError as exc:
        logger.warning("generate_schema: validation error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except InvalidSchemaTypeError as exc:
        logger.warning("generate_schema: invalid schema type: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except SchemaGenerationError as exc:
        logger.error("generate_schema: generation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Schema generation failed",
        ) from exc
    except Exception as exc:
        logger.error("generate_schema: unexpected error: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred during schema generation",
        ) from exc


@router.post(
    "/audit",
    response_model=SchemaAuditResponse,
    status_code=status.HTTP_200_OK,
    summary="Audit existing schema markup on a URL",
    description="Fetch a URL and extract all JSON-LD schema markup using extruct. Returns detected schemas with their types and properties.",
)
async def audit_schema(
    body: SchemaAuditRequest,
    db: AsyncSession = Depends(get_db),
) -> SchemaAuditResponse:
    try:
        service = SchemaGenerationService(db)
        return await service.audit_schema(body)
    except ValidationError as exc:
        logger.warning("audit_schema: validation error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except SchemaAuditError as exc:
        logger.error("audit_schema: audit failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.error("audit_schema: unexpected error: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred during schema audit",
        ) from exc


@router.get(
    "/types",
    response_model=SchemaTypesResponse,
    status_code=status.HTTP_200_OK,
    summary="List supported schema types",
    description="Returns information about all supported schema types, their subtypes, required fields, and recommended fields.",
)
async def list_schema_types() -> SchemaTypesResponse:
    types = [
        SchemaTypeInfo(
            type="organization",
            required_fields=["name", "url", "logo"],
            recommended_fields=["sameAs", "email", "telephone", "address"],
            description="Company or organization information",
        ),
        SchemaTypeInfo(
            type="local_business",
            subtypes=["restaurant", "store", "medical_business", "professional_service"],
            required_fields=["name", "url", "logo", "address"],
            recommended_fields=[
                "sameAs",
                "email",
                "telephone",
                "openingHours",
                "priceRange",
                "geo",
            ],
            description="Physical business with location and hours",
        ),
        SchemaTypeInfo(
            type="article",
            subtypes=["article", "blog_posting", "news_article"],
            required_fields=["headline", "image", "datePublished", "author", "publisher"],
            recommended_fields=[
                "dateModified",
                "articleSection",
                "articleBody",
                "keywords",
            ],
            description="Content pages: articles, blog posts, news",
        ),
        SchemaTypeInfo(
            type="product",
            required_fields=["name", "image", "offers"],
            recommended_fields=[
                "description",
                "sku",
                "brand",
                "aggregateRating",
                "review",
                "gtin",
            ],
            description="E-commerce products with pricing and reviews",
        ),
    ]
    return SchemaTypesResponse(types=types)