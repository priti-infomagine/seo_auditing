import time
from typing import Any

import extruct
import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import logger

from .exceptions import (
    InvalidSchemaTypeError,
    SchemaAuditError,
    SchemaGenerationError,
)
from .generator import SchemaGenerator
from .model import ArticleSubType, GenerationStatus, SchemaAudit, SchemaGeneration, SchemaType
from .repository import SchemaAuditRepository, SchemaGenerationRepository
from .schema import (
    ArticleInput,
    LocalBusinessInput,
    OrganizationInput,
    ProductInput,
    SchemaAuditRequest,
    SchemaAuditResponse,
    SchemaGenerateRequest,
    SchemaGenerateResponse,
)


class SchemaGenerationService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.generation_repo = SchemaGenerationRepository(db)
        self.audit_repo = SchemaAuditRepository(db)
        self.generator = SchemaGenerator()

    async def generate_schema(
        self, request: SchemaGenerateRequest
    ) -> SchemaGenerateResponse:
        start_time = time.perf_counter()
        try:
            if request.schema_type not in SchemaType:
                raise InvalidSchemaTypeError(
                    f"Unsupported schema type: {request.schema_type}"
                )

            json_ld, warnings = self._build_jsonld(request)

            record = SchemaGeneration(
                schema_type=request.schema_type.value,
                article_subtype=request.article_subtype.value
                if request.article_subtype
                else None,
                input_data=request.input_data.model_dump(mode="json"),
                generated_jsonld=json_ld,
                warnings=warnings,
                status=GenerationStatus.COMPLETED.value,
                cost_seconds=round(time.perf_counter() - start_time, 3),
            )
            await self.generation_repo.create(record)
            await self.db.commit()

            return SchemaGenerateResponse(
                schema_type=request.schema_type,
                article_subtype=request.article_subtype,
                generated_jsonld=json_ld,
                warnings=warnings,
                generation_id=record.id,
                cost_seconds=record.cost_seconds,
            )

        except InvalidSchemaTypeError:
            raise
        except Exception as exc:
            logger.error(f"Schema generation failed: {exc}", exc_info=True)
            record = SchemaGeneration(
                schema_type=request.schema_type.value
                if request.schema_type in SchemaType
                else "unknown",
                article_subtype=request.article_subtype.value
                if request.article_subtype
                else None,
                input_data=request.input_data.model_dump(mode="json"),
                status=GenerationStatus.FAILED.value,
                error=str(exc),
                cost_seconds=round(time.perf_counter() - start_time, 3),
            )
            await self.generation_repo.create(record)
            await self.db.commit()
            raise SchemaGenerationError(str(exc))

    def _build_jsonld(
        self, request: SchemaGenerateRequest
    ) -> tuple[dict[str, Any], list[str]]:
        input_data = request.input_data

        if request.schema_type == SchemaType.ORGANIZATION:
            if not isinstance(input_data, OrganizationInput):
                raise SchemaGenerationError(
                    "Input data must be OrganizationInput for Organization schema"
                )
            return self.generator.build_organization(input_data)

        elif request.schema_type == SchemaType.LOCAL_BUSINESS:
            if not isinstance(input_data, LocalBusinessInput):
                raise SchemaGenerationError(
                    "Input data must be LocalBusinessInput for LocalBusiness schema"
                )
            return self.generator.build_local_business(input_data)

        elif request.schema_type == SchemaType.ARTICLE:
            if not isinstance(input_data, ArticleInput):
                raise SchemaGenerationError(
                    "Input data must be ArticleInput for Article schema"
                )
            return self.generator.build_article(input_data, request.article_subtype)

        elif request.schema_type == SchemaType.PRODUCT:
            if not isinstance(input_data, ProductInput):
                raise SchemaGenerationError(
                    "Input data must be ProductInput for Product schema"
                )
            return self.generator.build_product(input_data)

        else:
            raise InvalidSchemaTypeError(
                f"Unsupported schema type: {request.schema_type}"
            )

    async def audit_schema(self, request: SchemaAuditRequest) -> SchemaAuditResponse:
        start_time = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    request.url,
                    headers={"User-Agent": "SEOAuditBot/1.0"},
                    follow_redirects=True,
                )

            if response.status_code != 200:
                raise SchemaAuditError(
                    f"Failed to fetch URL: HTTP {response.status_code}"
                )

            extracted = extruct.extract(
                response.text, base_url=request.url, syntaxes=["json-ld"]
            )
            json_ld_blocks = extracted.get("json-ld", [])

            record = SchemaAudit(
                url=request.url,
                detected_schemas=json_ld_blocks,
                status="completed",
                cost_seconds=round(time.perf_counter() - start_time, 3),
            )
            await self.audit_repo.create(record)
            await self.db.commit()

            return SchemaAuditResponse(
                url=request.url,
                detected_schemas=json_ld_blocks,
                schema_count=len(json_ld_blocks),
                audit_id=record.id,
                cost_seconds=record.cost_seconds,
            )

        except SchemaAuditError:
            raise
        except httpx.TimeoutException as exc:
            logger.error(f"Schema audit timeout for {request.url}: {exc}")
            record = SchemaAudit(
                url=request.url,
                status="failed",
                error=f"Timeout: {exc}",
                cost_seconds=round(time.perf_counter() - start_time, 3),
            )
            await self.audit_repo.create(record)
            await self.db.commit()
            raise SchemaAuditError(f"Request timeout: {exc}")
        except httpx.RequestError as exc:
            logger.error(f"Schema audit request error for {request.url}: {exc}")
            record = SchemaAudit(
                url=request.url,
                status="failed",
                error=f"Request error: {exc}",
                cost_seconds=round(time.perf_counter() - start_time, 3),
            )
            await self.audit_repo.create(record)
            await self.db.commit()
            raise SchemaAuditError(f"Request failed: {exc}")
        except Exception as exc:
            logger.error(f"Schema audit failed for {request.url}: {exc}", exc_info=True)
            record = SchemaAudit(
                url=request.url,
                status="failed",
                error=str(exc),
                cost_seconds=round(time.perf_counter() - start_time, 3),
            )
            await self.audit_repo.create(record)
            await self.db.commit()
            raise SchemaAuditError(str(exc))