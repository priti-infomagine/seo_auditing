from typing import Any, List, Optional, Union
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, HttpUrl, field_validator

from .model import ArticleSubType, SchemaType


class PostalAddressInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    streetAddress: str = Field(alias="streetAddress")
    addressLocality: str = Field(alias="addressLocality")
    addressRegion: str = Field(alias="addressRegion")
    postalCode: str = Field(alias="postalCode")
    addressCountry: str = Field(alias="addressCountry")


class GeoCoordinatesInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    latitude: float = Field(alias="latitude")
    longitude: float = Field(alias="longitude")


class PersonInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str
    url: Optional[HttpUrl] = None
    image: Optional[HttpUrl] = None
    sameAs: Optional[List[HttpUrl]] = Field(default=None, alias="sameAs")


class OrganizationInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str
    url: HttpUrl
    logo: HttpUrl
    sameAs: Optional[List[HttpUrl]] = Field(default=None, alias="sameAs")
    email: Optional[EmailStr] = None
    telephone: Optional[str] = None
    address: Optional[PostalAddressInput] = None


class LocalBusinessInput(OrganizationInput):
    address: PostalAddressInput
    openingHours: Optional[List[str]] = Field(default=None, alias="openingHours")
    priceRange: Optional[str] = Field(default=None, alias="priceRange")
    geo: Optional[GeoCoordinatesInput] = None
    additionalType: Optional[str] = Field(default=None, alias="additionalType")


class ArticleInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    headline: str
    image: Union[HttpUrl, List[HttpUrl]] = Field(alias="image")
    datePublished: str = Field(alias="datePublished")
    dateModified: Optional[str] = Field(default=None, alias="dateModified")
    author: Union[PersonInput, List[PersonInput], str] = Field(alias="author")
    publisher: OrganizationInput = Field(alias="publisher")
    articleSection: Optional[str] = Field(default=None, alias="articleSection")
    articleBody: Optional[str] = Field(default=None, alias="articleBody")
    keywords: Optional[str] = None
    wordCount: Optional[int] = None


class OfferInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    price: str = Field(alias="price")
    priceCurrency: str = Field(alias="priceCurrency")
    availability: Optional[str] = Field(default=None, alias="availability")
    seller: Optional[OrganizationInput] = None
    validFrom: Optional[str] = Field(default=None, alias="validFrom")
    validThrough: Optional[str] = Field(default=None, alias="validThrough")


class AggregateRatingInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    ratingValue: float = Field(alias="ratingValue")
    reviewCount: int = Field(alias="reviewCount")
    bestRating: Optional[float] = Field(default=None, alias="bestRating")
    worstRating: Optional[float] = Field(default=None, alias="worstRating")


class ReviewInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    author: PersonInput = Field(alias="author")
    reviewRating: AggregateRatingInput = Field(alias="reviewRating")
    reviewBody: Optional[str] = Field(default=None, alias="reviewBody")
    datePublished: str = Field(alias="datePublished")
    publisher: Optional[OrganizationInput] = None


class ProductInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str
    image: Union[HttpUrl, List[HttpUrl]] = Field(alias="image")
    description: Optional[str] = None
    sku: Optional[str] = None
    mpn: Optional[str] = None
    brand: Optional[OrganizationInput] = Field(default=None, alias="brand")
    offers: Union[OfferInput, List[OfferInput]] = Field(alias="offers")
    aggregateRating: Optional[AggregateRatingInput] = Field(default=None, alias="aggregateRating")
    review: Optional[List[ReviewInput]] = Field(default=None, alias="review")
    gtin: Optional[str] = None
    mpn: Optional[str] = None


class SchemaGenerateRequest(BaseModel):
    schema_type: SchemaType
    article_subtype: Optional[ArticleSubType] = None
    input_data: Union[
        OrganizationInput,
        LocalBusinessInput,
        ArticleInput,
        ProductInput,
    ]


class SchemaAuditRequest(BaseModel):
    url: str = Field(..., min_length=1)

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("url must not be empty")
        if not cleaned.startswith(("http://", "https://")):
            cleaned = f"https://{cleaned}"
        return cleaned


class SchemaGenerateResponse(BaseModel):
    schema_type: SchemaType
    article_subtype: Optional[ArticleSubType] = None
    generated_jsonld: dict[str, Any]
    warnings: List[str] = Field(default_factory=list)
    generation_id: UUID
    cost_seconds: Optional[float] = None


class SchemaAuditResponse(BaseModel):
    url: str
    detected_schemas: List[dict[str, Any]] = Field(default_factory=list)
    schema_count: int = 0
    audit_id: UUID
    cost_seconds: Optional[float] = None


class SchemaTypeInfo(BaseModel):
    type: SchemaType
    subtypes: List[str] = Field(default_factory=list)
    required_fields: List[str] = Field(default_factory=list)
    recommended_fields: List[str] = Field(default_factory=list)
    description: str


class SchemaTypesResponse(BaseModel):
    types: List[SchemaTypeInfo]