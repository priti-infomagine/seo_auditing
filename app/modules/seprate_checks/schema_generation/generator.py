from typing import Any, List, Optional, Union

from .schema import (
    AnswerInput,
    ArticleInput,
    EventInput,
    FAQPageInput,
    HowToInput,
    HowToStepInput,
    JobPostingInput,
    LocalBusinessInput,
    MonetaryAmountInput,
    OfferInput,
    OpeningHoursSpecificationInput,
    OrganizationInput,
    OrganizationRefInput,
    PersonInput,
    PlaceInput,
    PostalAddressInput,
    ProductInput,
    QuantitativeValueInput,
    QuestionInput,
    SearchActionInput,
    VirtualLocationInput,
    WebsiteInput,
    AggregateRatingInput,
    ReviewInput,
)
from .model import ArticleSubType, LocalBusinessSubType, SchemaType


class SchemaGenerator:
    """Core JSON-LD schema builder with registry pattern."""

    def __init__(self):
        self._builders = {
            SchemaType.ORGANIZATION: self.build_organization,
            SchemaType.LOCAL_BUSINESS: self.build_local_business,
            SchemaType.ARTICLE: self.build_article,
            SchemaType.PRODUCT: self.build_product,
            SchemaType.WEBSITE: self.build_website,
            SchemaType.EVENT: self.build_event,
            SchemaType.JOB_POSTING: self.build_job_posting,
            SchemaType.FAQ_PAGE: self.build_faq_page,
            SchemaType.HOW_TO: self.build_how_to,
        }

    def build(
        self,
        schema_type: SchemaType,
        article_subtype: Optional[ArticleSubType],
        local_business_subtype: Optional[LocalBusinessSubType],
        input_data: Union[
            OrganizationInput,
            LocalBusinessInput,
            ArticleInput,
            ProductInput,
            WebsiteInput,
            EventInput,
            JobPostingInput,
            FAQPageInput,
            HowToInput,
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
        if schema_type == SchemaType.LOCAL_BUSINESS:
            return builder(input_data, local_business_subtype)
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

        if data.contactPoint:
            json_ld["contactPoint"] = {
                "@type": "ContactPoint",
                "telephone": data.contactPoint.telephone,
                "contactType": data.contactPoint.contactType,
            }
            if data.contactPoint.contactOption:
                json_ld["contactPoint"]["contactOption"] = data.contactPoint.contactOption
            if data.contactPoint.areaServed:
                json_ld["contactPoint"]["areaServed"] = data.contactPoint.areaServed
            if data.contactPoint.availableLanguage:
                json_ld["contactPoint"]["availableLanguage"] = data.contactPoint.availableLanguage
        else:
            warnings.append("Missing recommended field: contactPoint")

        return json_ld, warnings

    def build_local_business(
        self, data: LocalBusinessInput, local_business_subtype: Optional[LocalBusinessSubType]
    ) -> tuple[dict[str, Any], List[str]]:
        warnings = []
        schema_type = local_business_subtype.value if local_business_subtype else "LocalBusiness"
        
        json_ld = {
            "@context": "https://schema.org",
            "@type": schema_type,
            "name": data.name,
            "url": str(data.url),
            "logo": str(data.logo),
            "address": self._build_address(data.address),
        }

        if data.sameAs:
            json_ld["sameAs"] = [str(url) for url in data.sameAs]
        else:
            warnings.append("Missing recommended field: sameAs (social media links)")

        if data.contactPoint:
            json_ld["contactPoint"] = {
                "@type": "ContactPoint",
                "telephone": data.contactPoint.telephone,
                "contactType": data.contactPoint.contactType,
            }
            if data.contactPoint.contactOption:
                json_ld["contactPoint"]["contactOption"] = data.contactPoint.contactOption
            if data.contactPoint.areaServed:
                json_ld["contactPoint"]["areaServed"] = data.contactPoint.areaServed
            if data.contactPoint.availableLanguage:
                json_ld["contactPoint"]["availableLanguage"] = data.contactPoint.availableLanguage
            if data.contactPoint.email:
                json_ld["contactPoint"]["email"] = data.contactPoint.email
        else:
            warnings.append("Missing recommended field: contactPoint")

        if data.openingHoursSpecification:
            json_ld["openingHoursSpecification"] = [
                self._build_opening_hours_spec(spec) for spec in data.openingHoursSpecification
            ]
        else:
            warnings.append("Missing recommended field: openingHoursSpecification")

        if data.priceRange:
            json_ld["priceRange"] = data.priceRange

        if data.servesCuisine:
            json_ld["servesCuisine"] = data.servesCuisine

        if data.geo:
            json_ld["geo"] = {
                "@type": "GeoCoordinates",
                "latitude": data.geo.latitude,
                "longitude": data.geo.longitude,
            }

        if data.image:
            json_ld["image"] = [str(img) for img in data.image]

        if data.description:
            json_ld["description"] = data.description

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

        if data.description:
            json_ld["description"] = data.description

        if data.mainEntityOfPage:
            json_ld["mainEntityOfPage"] = data.mainEntityOfPage
        else:
            warnings.append("Missing recommended field: mainEntityOfPage")

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

        if data.aggregateRating:
            json_ld["aggregateRating"] = self._build_aggregate_rating(
                data.aggregateRating
            )
        else:
            warnings.append("Missing recommended field: aggregateRating")

        # Google requires either offers or aggregateRating for Product rich results
        if not data.offers and not data.aggregateRating:
            warnings.append("Missing recommended field: offers or aggregateRating (at least one is required for Product rich results)")

        if data.review:
            json_ld["review"] = [self._build_review(review) for review in data.review]

        return json_ld, warnings

    def build_website(
        self, data: WebsiteInput
    ) -> tuple[dict[str, Any], List[str]]:
        warnings = []
        json_ld = {
            "@context": "https://schema.org",
            "@type": "WebSite",
            "name": data.name,
            "url": str(data.url),
        }

        if data.alternateName:
            json_ld["alternateName"] = (
                [str(name) for name in data.alternateName]
                if isinstance(data.alternateName, list)
                else data.alternateName
            )

        if data.potentialAction:
            json_ld["potentialAction"] = self._build_search_action(
                data.potentialAction
            )
        else:
            warnings.append(
                "Missing recommended field: potentialAction (SearchAction for sitelinks searchbox)"
            )

        return json_ld, warnings

    def build_event(
        self, data: EventInput
    ) -> tuple[dict[str, Any], List[str]]:
        warnings = []
        json_ld = {
            "@context": "https://schema.org",
            "@type": "Event",
            "name": data.name,
            "startDate": data.startDate,
            "location": self._build_event_location(data.location),
        }

        if data.endDate:
            json_ld["endDate"] = data.endDate
        else:
            warnings.append("Missing recommended field: endDate")

        if data.description:
            json_ld["description"] = data.description

        if data.image:
            json_ld["image"] = (
                [str(img) for img in data.image]
                if isinstance(data.image, list)
                else str(data.image)
            )
        else:
            warnings.append("Missing recommended field: image")

        if data.offers:
            offers = data.offers if isinstance(data.offers, list) else [data.offers]
            json_ld["offers"] = [self._build_offer(offer) for offer in offers]

        if data.organizer:
            json_ld["organizer"] = self._build_event_actor(data.organizer)

        if data.performer:
            performers = (
                data.performer
                if isinstance(data.performer, list)
                else [data.performer]
            )
            json_ld["performer"] = [
                self._build_event_actor(performer) for performer in performers
            ]

        if data.eventStatus:
            json_ld["eventStatus"] = self._schema_org_url(data.eventStatus)

        if data.eventAttendanceMode:
            json_ld["eventAttendanceMode"] = self._schema_org_url(
                data.eventAttendanceMode
            )

        if data.previousStartDate:
            json_ld["previousStartDate"] = data.previousStartDate

        return json_ld, warnings

    def build_job_posting(
        self, data: JobPostingInput
    ) -> tuple[dict[str, Any], List[str]]:
        warnings = []
        json_ld = {
            "@context": "https://schema.org",
            "@type": "JobPosting",
            "title": data.title,
            "description": data.description,
            "datePosted": data.datePosted,
            "hiringOrganization": self._build_organization_ref(
                data.hiringOrganization
            ),
        }

        if data.jobLocation:
            json_ld["jobLocation"] = self._build_place(data.jobLocation)
        elif data.jobLocationType:
            json_ld["jobLocationType"] = data.jobLocationType
            if data.applicantLocationRequirements:
                json_ld["applicantLocationRequirements"] = (
                    data.applicantLocationRequirements
                )
        else:
            warnings.append(
                "Missing required field: jobLocation (or jobLocationType for remote jobs)"
            )

        if data.validThrough:
            json_ld["validThrough"] = data.validThrough

        if data.employmentType:
            json_ld["employmentType"] = (
                [str(t) for t in data.employmentType]
                if isinstance(data.employmentType, list)
                else data.employmentType
            )

        if data.baseSalary:
            json_ld["baseSalary"] = self._build_monetary_amount(data.baseSalary)

        if data.jobBenefits:
            json_ld["jobBenefits"] = data.jobBenefits

        if data.educationRequirements:
            json_ld["educationRequirements"] = data.educationRequirements

        if data.experienceRequirements:
            json_ld["experienceRequirements"] = data.experienceRequirements

        if data.qualifications:
            json_ld["qualifications"] = data.qualifications

        if data.responsibilities:
            json_ld["responsibilities"] = data.responsibilities

        if data.skills:
            json_ld["skills"] = data.skills

        if data.workHours:
            json_ld["workHours"] = data.workHours

        if data.directApply is not None:
            json_ld["directApply"] = data.directApply

        if data.identifier:
            json_ld["identifier"] = data.identifier

        return json_ld, warnings

    def build_faq_page(
        self, data: FAQPageInput
    ) -> tuple[dict[str, Any], List[str]]:
        warnings = []
        json_ld = {
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "mainEntity": [
                self._build_question(question) for question in data.mainEntity
            ],
        }

        if not data.mainEntity:
            warnings.append("FAQPage should contain at least one Question")

        return json_ld, warnings

    def build_how_to(
        self, data: HowToInput
    ) -> tuple[dict[str, Any], List[str]]:
        warnings = []
        json_ld = {
            "@context": "https://schema.org",
            "@type": "HowTo",
            "name": data.name,
            "step": [self._build_how_to_step(step) for step in data.step],
        }

        if not data.step:
            warnings.append("HowTo should contain at least one HowToStep")

        if data.description:
            json_ld["description"] = data.description

        if data.image:
            json_ld["image"] = (
                [str(img) for img in data.image]
                if isinstance(data.image, list)
                else str(data.image)
            )

        if data.totalTime:
            json_ld["totalTime"] = data.totalTime

        if data.estimatedCost:
            json_ld["estimatedCost"] = self._build_monetary_amount(
                data.estimatedCost
            )

        if data.supply:
            json_ld["supply"] = [
                {"@type": "HowToSupply", "name": supply.name}
                for supply in data.supply
            ]

        if data.tool:
            json_ld["tool"] = [
                {"@type": "HowToTool", "name": tool.name} for tool in data.tool
            ]

        if data.video:
            json_ld["video"] = data.video

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

    def _build_opening_hours_spec(self, spec: OpeningHoursSpecificationInput) -> dict[str, Any]:
        return {
            "@type": "OpeningHoursSpecification",
            "dayOfWeek": spec.dayOfWeek,
            "opens": spec.opens,
            "closes": spec.closes,
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

    def _build_publisher(self, publisher: OrganizationRefInput) -> dict[str, Any]:
        return {
            "@type": "Organization",
            "name": publisher.name,
            "logo": {
                "@type": "ImageObject",
                "url": str(publisher.logo),
            },
        }

    def _build_organization_ref(self, org: OrganizationRefInput) -> dict[str, Any]:
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

    def _build_search_action(
        self, action: SearchActionInput
    ) -> dict[str, Any]:
        target = action.target
        if isinstance(target, str):
            target_obj: dict[str, Any] = {
                "@type": "EntryPoint",
                "urlTemplate": target,
            }
        else:
            target_obj = dict(target)
            target_obj.setdefault("@type", "EntryPoint")
        return {
            "@type": "SearchAction",
            "target": target_obj,
            "query-input": action.queryInput,
        }

    def _build_event_location(
        self, location: Union[PlaceInput, VirtualLocationInput]
    ) -> dict[str, Any]:
        if isinstance(location, VirtualLocationInput):
            return self._build_virtual_location(location)
        return self._build_place(location)

    def _build_event_actor(
        self, actor: Union[PersonInput, OrganizationRefInput]
    ) -> dict[str, Any]:
        if isinstance(actor, PersonInput):
            return self._build_person(actor)
        return self._build_organization_ref(actor)

    def _build_place(self, place: PlaceInput) -> dict[str, Any]:
        return {
            "@type": "Place",
            "name": place.name,
            "address": self._build_address(place.address),
        }

    def _build_virtual_location(
        self, location: VirtualLocationInput
    ) -> dict[str, Any]:
        return {
            "@type": "VirtualLocation",
            "url": str(location.url),
        }

    def _build_monetary_amount(
        self, amount: MonetaryAmountInput
    ) -> dict[str, Any]:
        result = {
            "@type": "MonetaryAmount",
            "currency": amount.currency,
        }
        if isinstance(amount.value, QuantitativeValueInput):
            result["value"] = self._build_quantitative_value(amount.value)
        else:
            result["value"] = amount.value
        return result

    def _build_quantitative_value(
        self, value: QuantitativeValueInput
    ) -> dict[str, Any]:
        result = {
            "@type": "QuantitativeValue",
            "value": value.value,
        }
        if value.unitText:
            result["unitText"] = value.unitText
        return result

    def _build_question(self, question: QuestionInput) -> dict[str, Any]:
        return {
            "@type": "Question",
            "name": question.name,
            "acceptedAnswer": self._build_answer(question.acceptedAnswer),
        }

    def _build_answer(self, answer: AnswerInput) -> dict[str, Any]:
        return {
            "@type": "Answer",
            "text": answer.text,
        }

    def _build_how_to_step(self, step: HowToStepInput) -> dict[str, Any]:
        result = {
            "@type": "HowToStep",
            "text": step.text,
        }
        if step.name:
            result["name"] = step.name
        if step.image:
            result["image"] = (
                [str(img) for img in step.image]
                if isinstance(step.image, list)
                else str(step.image)
            )
        if step.url:
            result["url"] = str(step.url)
        return result

    @staticmethod
    def _schema_org_url(value: str) -> str:
        if value.startswith("https://schema.org/"):
            return value
        if value.startswith("schema.org/"):
            return f"https://{value}"
        return f"https://schema.org/{value}"