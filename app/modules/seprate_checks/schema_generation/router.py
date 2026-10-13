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
    description="Generate valid JSON-LD structured data for SEO. Supports Organization, LocalBusiness, Article (BlogPosting, NewsArticle), Product, WebSite, Event, JobPosting, FAQPage, and HowTo schema types.",
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
            recommended_fields=["sameAs", "contactPoint", "address", "description"],
            description="Company or organization information (knowledge panel, sameAs links)",
        ),
        SchemaTypeInfo(
            type="local_business",
            subtypes=["restaurant", "store", "medical_business", "professional_service", "automotive_business", "child_care", "dentist", "electrician", "financial_service", "food_establishment", "health_and_beauty_business", "legal_service", "lodging_business", "medical_clinic", "pharmacy", "physician", "real_estate_agent", "store", "travel_agency", "veterinary_care"],
            required_fields=["name", "url", "logo", "address"],
            recommended_fields=[
                "sameAs",
                "contactPoint",
                "image",
                "openingHoursSpecification",
                "priceRange",
                "geo",
                "servesCuisine",
                "description",
            ],
            description="Physical business with location and hours (Local Pack, Maps)",
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
                "description",
                "mainEntityOfPage",
            ],
            description="Content pages: articles, blog posts, news (Top Stories, Discover)",
        ),
        SchemaTypeInfo(
            type="product",
            required_fields=["name", "image", "offers"],
            recommended_fields=[
                "description",
                "sku",
                "mpn",
                "gtin",
                "brand",
                "aggregateRating",
                "review",
            ],
            description="E-commerce products with pricing and reviews (Product Snippet, Merchant Listing)",
        ),
        SchemaTypeInfo(
            type="website",
            required_fields=["name", "url"],
            recommended_fields=["alternateName", "potentialAction"],
            description="Site name and sitelinks searchbox (Site Names, Sitelinks Searchbox). Must be on home page only.",
        ),
        SchemaTypeInfo(
            type="event",
            required_fields=["name", "startDate", "location"],
            recommended_fields=[
                "endDate",
                "description",
                "image",
                "offers",
                "organizer",
                "performer",
                "eventStatus",
                "eventAttendanceMode",
            ],
            description="Events with date and location (Event rich results). Use VirtualLocation for online events.",
        ),
        SchemaTypeInfo(
            type="job_posting",
            required_fields=["title", "description", "datePosted", "hiringOrganization", "jobLocation"],
            recommended_fields=[
                "validThrough",
                "employmentType",
                "baseSalary",
                "jobBenefits",
                "educationRequirements",
                "experienceRequirements",
                "qualifications",
                "responsibilities",
                "skills",
                "workHours",
                "directApply",
                "identifier",
            ],
            description="Job listings (Google Jobs). For remote jobs use jobLocationType=TELECOMMUTE with applicantLocationRequirements.",
        ),
        SchemaTypeInfo(
            type="faq_page",
            required_fields=["mainEntity"],
            recommended_fields=[],
            description="Frequently asked questions (FAQ rich results). Note: currently shown only for well-known, authoritative government-focused or health-focused websites. One FAQPage per page.",
        ),
        SchemaTypeInfo(
            type="how_to",
            required_fields=["name", "step"],
            recommended_fields=[
                "description",
                "image",
                "totalTime",
                "estimatedCost",
                "supply",
                "tool",
                "video",
            ],
            description="Step-by-step instructions (How-to rich results). Note: desktop only; deprecated for mobile in Sep 2023. Do not use for recipes or advertising.",
        ),
    ]
    return SchemaTypesResponse(types=types)