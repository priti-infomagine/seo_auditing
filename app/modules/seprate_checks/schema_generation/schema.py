from typing import Any, Dict, List, Optional, Union
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, HttpUrl, field_validator, model_serializer

from .model import ArticleSubType, LocalBusinessSubType, SchemaType


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


class OpeningHoursSpecificationInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    dayOfWeek: List[str] = Field(alias="dayOfWeek")
    opens: str = Field(alias="opens")
    closes: str = Field(alias="closes")


class PersonInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str
    url: Optional[HttpUrl] = None
    image: Optional[HttpUrl] = None
    sameAs: Optional[List[HttpUrl]] = Field(default=None, alias="sameAs")


class OrganizationRefInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str
    url: Optional[HttpUrl] = None
    logo: Optional[HttpUrl] = None


class ContactPointInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    telephone: str
    contactType: str = Field(default="customer service", alias="contactType")
    email: Optional[EmailStr] = None
    areaServed: Optional[str] = Field(default=None, alias="areaServed")
    availableLanguage: Optional[List[str]] = Field(default=None, alias="availableLanguage")
    contactOption: Optional[str] = Field(default=None, alias="contactOption")


class OrganizationInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str
    url: HttpUrl
    logo: HttpUrl
    sameAs: Optional[List[HttpUrl]] = Field(default=None, alias="sameAs")
    address: Optional[PostalAddressInput] = None
    contactPoint: Optional[ContactPointInput] = Field(default=None, alias="contactPoint")
    description: Optional[str] = None


class LocalBusinessInput(OrganizationInput):
    address: PostalAddressInput
    image: Optional[List[HttpUrl]] = None
    geo: Optional[GeoCoordinatesInput] = None
    openingHoursSpecification: Optional[List[OpeningHoursSpecificationInput]] = Field(default=None, alias="openingHoursSpecification")
    priceRange: Optional[str] = None
    servesCuisine: Optional[str] = None
    additionalType: Optional[str] = Field(default=None, alias="additionalType")


class ArticleInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    headline: str
    image: Union[HttpUrl, List[HttpUrl]] = Field(alias="image")
    datePublished: str = Field(alias="datePublished")
    dateModified: Optional[str] = Field(default=None, alias="dateModified")
    author: Union[PersonInput, List[PersonInput], str] = Field(alias="author")
    publisher: OrganizationRefInput = Field(alias="publisher")
    description: Optional[str] = None
    mainEntityOfPage: Optional[Dict[str, Any]] = Field(default=None, alias="mainEntityOfPage")
    articleSection: Optional[str] = Field(default=None, alias="articleSection")
    articleBody: Optional[str] = Field(default=None, alias="articleBody")
    keywords: Optional[str] = None
    wordCount: Optional[int] = None


class OfferInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    price: str = Field(alias="price")
    priceCurrency: str = Field(alias="priceCurrency")
    availability: Optional[str] = Field(default=None, alias="availability")
    url: Optional[HttpUrl] = None
    priceValidUntil: Optional[str] = Field(default=None, alias="priceValidUntil")
    itemCondition: Optional[str] = Field(default=None, alias="itemCondition")
    seller: Optional[OrganizationRefInput] = None
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
    publisher: Optional[OrganizationRefInput] = None


class ProductInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str
    image: Union[HttpUrl, List[HttpUrl]] = Field(alias="image")
    description: Optional[str] = None
    sku: Optional[str] = None
    mpn: Optional[str] = None
    gtin: Optional[str] = None
    brand: Optional[OrganizationRefInput] = Field(default=None, alias="brand")
    offers: Optional[Union[OfferInput, List[OfferInput]]] = Field(default=None, alias="offers")
    aggregateRating: Optional[AggregateRatingInput] = Field(default=None, alias="aggregateRating")
    review: Optional[List[ReviewInput]] = Field(default=None, alias="review")


class SchemaGenerateRequest(BaseModel):
    schema_type: SchemaType
    article_subtype: Optional[ArticleSubType] = None
    local_business_subtype: Optional[LocalBusinessSubType] = None
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
    generated_jsonld: dict[str, Any]
    warnings: List[str] = Field(default_factory=list)
    generation_id: UUID
    cost_seconds: Optional[float] = None
    article_subtype: Optional[ArticleSubType] = None
    local_business_subtype: Optional[LocalBusinessSubType] = None

    @model_serializer(mode='wrap')
    def serialize_model(self, handler):
        data = handler(self)
        # Remove article_subtype if not article schema
        if data.get("schema_type") != "article":
            data.pop("article_subtype", None)
        # Remove local_business_subtype if not local_business schema
        if data.get("schema_type") != "local_business":
            data.pop("local_business_subtype", None)
        return data


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