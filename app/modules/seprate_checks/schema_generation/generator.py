from typing import Any, List, Optional, Union

from .schema import (
    ArticleInput,
    LocalBusinessInput,
    OfferInput,
    OrganizationInput,
    PersonInput,
    PostalAddressInput,
    ProductInput,
    AggregateRatingInput,
    ReviewInput,
)
from .model import ArticleSubType, SchemaType


class SchemaGenerator:
    """Core JSON-LD schema builder with registry pattern."""

    def __init__(self):
        self._builders = {
            SchemaType.ORGANIZATION: self.build_organization,
            SchemaType.LOCAL_BUSINESS: self.build_local_business,
            SchemaType.ARTICLE: self.build_article,
            SchemaType.PRODUCT: self.build_product,
        }

    def build(
        self,
        schema_type: SchemaType,
        article_subtype: Optional[ArticleSubType],
        input_data: Union[
            OrganizationInput,
            LocalBusinessInput,
            ArticleInput,
            ProductInput,
        ],
    ) -> tuple[dict[str, Any], List[str]]:
        """Build JSON-LD for the given schema type and input data.

        Returns:
            Tuple of (json_ld_dict, warnings_list)
        """
        builder = self._builders.get(schema_type)
        if not builder:
            raise ValueError(f"No builder for schema type: {schema_type}")

        if schema_type == SchemaType.ARTICLE:
            return builder(input_data, article_subtype)
        return builder(input_data)

    def build_organization(
        self, data: OrganizationInput
    ) -> tuple[dict[str, Any], List[str]]:
        warnings = []
        json_ld = {
            "@context": "https://schema.org",
            "@type": "Organization",
            "name": data.name,
            "url": str(data.url),
            "logo": str(data.logo),
        }

        if data.sameAs:
            json_ld["sameAs"] = [str(url) for url in data.sameAs]
        else:
            warnings.append("Missing recommended field: sameAs (social media links)")

        if data.email:
            json_ld["email"] = data.email
        else:
            warnings.append("Missing recommended field: email")

        if data.telephone:
            json_ld["telephone"] = data.telephone
        else:
            warnings.append("Missing recommended field: telephone")

        if data.address:
            json_ld["address"] = self._build_address(data.address)
        else:
            warnings.append("Missing recommended field: address")

        return json_ld, warnings

    def build_local_business(
        self, data: LocalBusinessInput
    ) -> tuple[dict[str, Any], List[str]]:
        warnings = []
        json_ld = {
            "@context": "https://schema.org",
            "@type": "LocalBusiness",
            "name": data.name,
            "url": str(data.url),
            "logo": str(data.logo),
            "address": self._build_address(data.address),
        }

        if data.sameAs:
            json_ld["sameAs"] = [str(url) for url in data.sameAs]
        else:
            warnings.append("Missing recommended field: sameAs (social media links)")

        if data.email:
            json_ld["email"] = data.email
        else:
            warnings.append("Missing recommended field: email")

        if data.telephone:
            json_ld["telephone"] = data.telephone
        else:
            warnings.append("Missing recommended field: telephone")

        if data.openingHours:
            json_ld["openingHours"] = data.openingHours
        else:
            warnings.append("Missing recommended field: openingHours")

        if data.priceRange:
            json_ld["priceRange"] = data.priceRange

        if data.geo:
            json_ld["geo"] = {
                "@type": "GeoCoordinates",
                "latitude": data.geo.latitude,
                "longitude": data.geo.longitude,
            }

        if data.additionalType:
            json_ld["additionalType"] = data.additionalType

        return json_ld, warnings

    def build_article(
        self, data: ArticleInput, article_subtype: Optional[ArticleSubType]
    ) -> tuple[dict[str, Any], List[str]]:
        warnings = []
        schema_type = article_subtype.value if article_subtype else "Article"

        json_ld = {
            "@context": "https://schema.org",
            "@type": schema_type,
            "headline": data.headline,
            "datePublished": data.datePublished,
            "author": self._build_author(data.author),
            "publisher": self._build_publisher(data.publisher),
        }

        if isinstance(data.image, list):
            json_ld["image"] = [str(img) for img in data.image]
        else:
            json_ld["image"] = str(data.image)

        if data.dateModified:
            json_ld["dateModified"] = data.dateModified
        else:
            warnings.append("Missing recommended field: dateModified")

        if data.articleSection:
            json_ld["articleSection"] = data.articleSection
        else:
            warnings.append("Missing recommended field: articleSection")

        if data.articleBody:
            json_ld["articleBody"] = data.articleBody
        else:
            warnings.append("Missing recommended field: articleBody")

        if data.keywords:
            json_ld["keywords"] = data.keywords

        if data.wordCount:
            json_ld["wordCount"] = data.wordCount

        return json_ld, warnings

    def build_product(
        self, data: ProductInput
    ) -> tuple[dict[str, Any], List[str]]:
        warnings = []
        json_ld = {
            "@context": "https://schema.org",
            "@type": "Product",
            "name": data.name,
            "image": [str(img) for img in data.image]
            if isinstance(data.image, list)
            else str(data.image),
        }

        if data.description:
            json_ld["description"] = data.description
        else:
            warnings.append("Missing recommended field: description")

        if data.sku:
            json_ld["sku"] = data.sku

        if data.mpn:
            json_ld["mpn"] = data.mpn

        if data.gtin:
            json_ld["gtin"] = data.gtin

        if data.brand:
            json_ld["brand"] = self._build_organization_ref(data.brand)

        if data.offers:
            offers = data.offers if isinstance(data.offers, list) else [data.offers]
            json_ld["offers"] = [self._build_offer(offer) for offer in offers]
        else:
            warnings.append("Missing required field: offers")

        if data.aggregateRating:
            json_ld["aggregateRating"] = self._build_aggregate_rating(
                data.aggregateRating
            )
        else:
            warnings.append("Missing recommended field: aggregateRating")

        if data.review:
            json_ld["review"] = [self._build_review(review) for review in data.review]

        return json_ld, warnings

    def _build_address(self, address: PostalAddressInput) -> dict[str, Any]:
        return {
            "@type": "PostalAddress",
            "streetAddress": address.streetAddress,
            "addressLocality": address.addressLocality,
            "addressRegion": address.addressRegion,
            "postalCode": address.postalCode,
            "addressCountry": address.addressCountry,
        }

    def _build_author(
        self, author: Union[PersonInput, List[PersonInput], str]
    ) -> Union[dict[str, Any], List[dict[str, Any]], str]:
        if isinstance(author, str):
            return {"@type": "Person", "name": author}
        if isinstance(author, list):
            return [self._build_person(a) for a in author]
        return self._build_person(author)

    def _build_person(self, person: PersonInput) -> dict[str, Any]:
        result = {"@type": "Person", "name": person.name}
        if person.url:
            result["url"] = str(person.url)
        if person.image:
            result["image"] = str(person.image)
        if person.sameAs:
            result["sameAs"] = [str(url) for url in person.sameAs]
        return result

    def _build_publisher(self, publisher: OrganizationInput) -> dict[str, Any]:
        return {
            "@type": "Organization",
            "name": publisher.name,
            "logo": {
                "@type": "ImageObject",
                "url": str(publisher.logo),
            },
        }

    def _build_organization_ref(self, org: OrganizationInput) -> dict[str, Any]:
        result = {"@type": "Organization", "name": org.name}
        if org.url:
            result["url"] = str(org.url)
        if org.logo:
            result["logo"] = str(org.logo)
        return result

    def _build_offer(self, offer: OfferInput) -> dict[str, Any]:
        result = {
            "@type": "Offer",
            "price": offer.price,
            "priceCurrency": offer.priceCurrency,
        }
        if offer.availability:
            result["availability"] = offer.availability
        if offer.seller:
            result["seller"] = self._build_organization_ref(offer.seller)
        if offer.validFrom:
            result["validFrom"] = offer.validFrom
        if offer.validThrough:
            result["validThrough"] = offer.validThrough
        return result

    def _build_aggregate_rating(self, rating: AggregateRatingInput) -> dict[str, Any]:
        result = {
            "@type": "AggregateRating",
            "ratingValue": rating.ratingValue,
            "reviewCount": rating.reviewCount,
        }
        if rating.bestRating is not None:
            result["bestRating"] = rating.bestRating
        if rating.worstRating is not None:
            result["worstRating"] = rating.worstRating
        return result

    def _build_review(self, review: ReviewInput) -> dict[str, Any]:
        return {
            "@type": "Review",
            "author": self._build_person(review.author),
            "reviewRating": self._build_aggregate_rating(review.reviewRating),
            "datePublished": review.datePublished,
            "reviewBody": review.reviewBody,
            "publisher": self._build_organization_ref(review.publisher)
            if review.publisher
            else None,
        }