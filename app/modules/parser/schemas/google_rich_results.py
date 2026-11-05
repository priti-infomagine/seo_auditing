"""
Google Rich Result Schema Type Registry.

Defines supported schema types, their required and recommended properties
for Google Rich Results eligibility.

Reference: https://developers.google.com/search/docs/appearance/structured-data
"""
from typing import Any


# Schema.org types that are eligible for Google Rich Results
GOOGLE_RICH_RESULT_TYPES: dict[str, dict[str, Any]] = {
    # Article types
    "Article": {
        "category": "Article",
        "required": ["headline", "image", "datePublished", "author"],
        "recommended": [
            "dateModified", "articleSection", "articleBody", "keywords",
            "description", "mainEntityOfPage", "publisher"
        ],
        "rich_result": "Article/NewsArticle/BlogPosting rich result",
    },
    "NewsArticle": {
        "category": "Article",
        "required": ["headline", "image", "datePublished", "author"],
        "recommended": [
            "dateModified", "articleSection", "articleBody", "keywords",
            "description", "mainEntityOfPage", "publisher"
        ],
        "rich_result": "Top Stories carousel",
    },
    "BlogPosting": {
        "category": "Article",
        "required": ["headline", "image", "datePublished", "author"],
        "recommended": [
            "dateModified", "articleSection", "articleBody", "keywords",
            "description", "mainEntityOfPage", "publisher"
        ],
        "rich_result": "Article rich result",
    },
    "ScholarlyArticle": {
        "category": "Article",
        "required": ["headline", "image", "datePublished", "author"],
        "recommended": ["dateModified", "articleSection", "articleBody", "keywords", "description"],
        "rich_result": "Article rich result",
    },

    # Product & E-commerce
    "Product": {
        "category": "Product",
        "required": ["name", "image", "offers"],
        "recommended": [
            "description", "sku", "mpn", "gtin", "brand",
            "aggregateRating", "review", "offers.price", "offers.priceCurrency",
            "offers.availability", "offers.seller"
        ],
        "rich_result": "Product snippet, Merchant listing",
    },
    "Offer": {
        "category": "Product",
        "required": ["price", "priceCurrency", "availability"],
        "recommended": ["seller", "validFrom", "priceValidUntil", "itemCondition"],
        "rich_result": "Product snippet (part of Product)",
    },
    "AggregateOffer": {
        "category": "Product",
        "required": ["price", "priceCurrency", "availability", "offerCount"],
        "recommended": ["lowPrice", "highPrice", "seller"],
        "rich_result": "Product snippet (part of Product)",
    },

    # Local Business
    "LocalBusiness": {
        "category": "LocalBusiness",
        "required": ["name", "address"],
        "recommended": [
            "url", "telephone", "openingHoursSpecification",
            "priceRange", "geo", "servesCuisine", "image",
            "aggregateRating", "review", "department"
        ],
        "rich_result": "Local Pack, Knowledge Panel",
        "subtypes": [
            "Restaurant", "Store", "MedicalBusiness", "ProfessionalService",
            "AutomotiveBusiness", "ChildCare", "Dentist", "Electrician",
            "FinancialService", "FoodEstablishment", "HealthAndBeautyBusiness",
            "LegalService", "LodgingBusiness", "MedicalClinic", "Pharmacy",
            "Physician", "RealEstateAgent", "TravelAgency", "VeterinaryCare"
        ],
    },
    "Organization": {
        "category": "Organization",
        "required": ["name", "url"],
        "recommended": [
            "logo", "sameAs", "contactPoint", "address", "description",
            "foundingDate", "duns", "taxID", "vatID", "employees"
        ],
        "rich_result": "Knowledge Panel, Sitelinks Searchbox",
    },

    # Events
    "Event": {
        "category": "Event",
        "required": ["name", "startDate", "location"],
        "recommended": [
            "endDate", "description", "image", "offers", "organizer",
            "performer", "eventStatus", "eventAttendanceMode",
            "maximumAttendeeCapacity", "remainingAttendeeCapacity"
        ],
        "rich_result": "Event rich result",
        "subtypes": [
            "BusinessEvent", "ChildrensEvent", "ComedyEvent", "CourseInstance",
            "DanceEvent", "DeliveryEvent", "EducationEvent", "ExhibitionEvent",
            "Festival", "FoodEvent", "Hackathon", "LiteraryEvent", "MusicEvent",
            "PublicationEvent", "SaleEvent", "ScreeningEvent", "SocialEvent",
            "SportsEvent", "TheaterEvent", "VisualArtsEvent"
        ],
    },

    # Job Posting
    "JobPosting": {
        "category": "JobPosting",
        "required": [
            "title", "description", "datePosted", "hiringOrganization", "jobLocation"
        ],
        "recommended": [
            "validThrough", "employmentType", "baseSalary", "jobBenefits",
            "educationRequirements", "experienceRequirements", "qualifications",
            "responsibilities", "skills", "workHours", "directApply",
            "identifier", "jobLocationType", "applicantLocationRequirements"
        ],
        "rich_result": "Google Jobs",
    },

    # FAQ & HowTo
    "FAQPage": {
        "category": "FAQ",
        "required": ["mainEntity"],
        "recommended": [],
        "rich_result": "FAQ rich result (authoritative sites only)",
        "note": "Only shown for well-known, authoritative government/health sites",
    },
    "Question": {
        "category": "FAQ",
        "required": ["name", "acceptedAnswer"],
        "recommended": ["suggestedAnswer"],
        "rich_result": "Part of FAQPage",
    },
    "Answer": {
        "category": "FAQ",
        "required": ["text"],
        "recommended": ["upvoteCount", "dateCreated", "author"],
        "rich_result": "Part of FAQPage/Question",
    },
    "HowTo": {
        "category": "HowTo",
        "required": ["name", "step"],
        "recommended": [
            "description", "image", "totalTime", "estimatedCost",
            "supply", "tool", "video", "yield"
        ],
        "rich_result": "How-to rich result (desktop only, deprecated mobile Sep 2023)",
        "note": "Do not use for recipes or advertising",
    },
    "HowToStep": {
        "category": "HowTo",
        "required": ["name", "itemListElement"],
        "recommended": ["description", "image", "video"],
        "rich_result": "Part of HowTo",
    },

    # Recipe
    "Recipe": {
        "category": "Recipe",
        "required": ["name", "recipeIngredient", "recipeInstructions"],
        "recommended": [
            "image", "author", "datePublished", "description",
            "prepTime", "cookTime", "totalTime", "recipeYield",
            "recipeCategory", "recipeCuisine", "keywords",
            "nutrition", "aggregateRating", "review", "video"
        ],
        "rich_result": "Recipe rich result, Recipe carousel",
    },

    # Breadcrumb
    "BreadcrumbList": {
        "category": "Navigation",
        "required": ["itemListElement"],
        "recommended": [],
        "rich_result": "Breadcrumb rich result",
    },
    "ListItem": {
        "category": "Navigation",
        "required": ["position", "item"],
        "recommended": [],
        "rich_result": "Part of BreadcrumbList",
    },

    # Video
    "VideoObject": {
        "category": "Video",
        "required": ["name", "description", "thumbnailUrl", "uploadDate"],
        "recommended": [
            "contentUrl", "embedUrl", "duration", "expires",
            "hasPart", "interactionStatistic", "regionsAllowed"
        ],
        "rich_result": "Video rich result, Video carousel",
    },

    # WebSite (Site Name + Sitelinks Searchbox)
    "WebSite": {
        "category": "WebSite",
        "required": ["name", "url"],
        "recommended": ["alternateName", "potentialAction"],
        "rich_result": "Site Names, Sitelinks Searchbox",
        "note": "Must be on home page only",
    },
    "SearchAction": {
        "category": "WebSite",
        "required": ["target", "query-input"],
        "recommended": [],
        "rich_result": "Sitelinks Searchbox (part of WebSite)",
    },

    # Person
    "Person": {
        "category": "Person",
        "required": ["name"],
        "recommended": [
            "url", "image", "sameAs", "jobTitle", "worksFor",
            "affiliation", "knowsAbout", "knowsLanguage"
        ],
        "rich_result": "Knowledge Panel (part of Article/Event/etc)",
    },

    # Review & Rating
    "Review": {
        "category": "Review",
        "required": ["author", "reviewRating", "datePublished"],
        "recommended": ["reviewBody", "itemReviewed", "publisher", "inLanguage"],
        "rich_result": "Review snippet (part of Product/LocalBusiness/etc)",
    },
    "AggregateRating": {
        "category": "Review",
        "required": ["ratingValue", "reviewCount"],
        "recommended": ["bestRating", "worstRating", "ratingCount"],
        "rich_result": "Review snippet (part of Product/LocalBusiness/etc)",
    },
    "Rating": {
        "category": "Review",
        "required": ["ratingValue"],
        "recommended": ["bestRating", "worstRating", "author"],
        "rich_result": "Part of Review/AggregateRating",
    },

    # Course
    "Course": {
        "category": "Course",
        "required": ["name", "provider"],
        "recommended": ["description", "hasCourseInstance", "url", "image"],
        "rich_result": "Course rich result",
    },
    "CourseInstance": {
        "category": "Course",
        "required": ["courseMode", "startDate", "endDate"],
        "recommended": ["location", "offers", "instructor", "description"],
        "rich_result": "Course rich result (part of Course)",
    },

    # Dataset
    "Dataset": {
        "category": "Dataset",
        "required": ["name", "description"],
        "recommended": ["url", "sameAs", "keywords", "license", "creator", "citation"],
        "rich_result": "Dataset rich result",
    },

    # Podcast
    "PodcastSeries": {
        "category": "Podcast",
        "required": ["name", "url", "description"],
        "recommended": ["image", "associatedMedia", "author", "publisher"],
        "rich_result": "Podcast rich result",
    },
    "PodcastEpisode": {
        "category": "Podcast",
        "required": ["name", "description", "associatedMedia"],
        "recommended": ["image", "datePublished", "duration", "partOfSeries"],
        "rich_result": "Podcast rich result (part of PodcastSeries)",
    },

    # Software Application
    "SoftwareApplication": {
        "category": "Software",
        "required": ["name", "applicationCategory", "offers"],
        "recommended": [
            "operatingSystem", "fileSize", "version", "releaseNotes",
            "aggregateRating", "review", "screenshot", "installUrl"
        ],
        "rich_result": "App rich result",
    },

    # Movie
    "Movie": {
        "category": "Movie",
        "required": ["name", "director"],
        "recommended": [
            "datePublished", "description", "duration", "genre",
            "actor", "aggregateRating", "review", "trailer"
        ],
        "rich_result": "Movie rich result",
    },

    # Book
    "Book": {
        "category": "Book",
        "required": ["name", "author"],
        "recommended": [
            "isbn", "datePublished", "description", "bookFormat",
            "numberOfPages", "publisher", "aggregateRating", "review", "offers"
        ],
        "rich_result": "Book rich result",
    },
}


def get_schema_requirements(schema_type: str) -> dict[str, Any] | None:
    """Get required/recommended properties for a schema type."""
    return GOOGLE_RICH_RESULT_TYPES.get(schema_type)


def is_google_rich_result_type(schema_type: str) -> bool:
    """Check if a schema type is eligible for Google Rich Results."""
    return schema_type in GOOGLE_RICH_RESULT_TYPES


def get_all_google_rich_result_types() -> list[str]:
    """Get list of all schema types eligible for Google Rich Results."""
    return list(GOOGLE_RICH_RESULT_TYPES.keys())


def get_schema_category(schema_type: str) -> str | None:
    """Get the category of a schema type."""
    info = GOOGLE_RICH_RESULT_TYPES.get(schema_type)
    return info.get("category") if info else None


def get_required_properties(schema_type: str) -> list[str]:
    """Get required properties for a schema type."""
    info = GOOGLE_RICH_RESULT_TYPES.get(schema_type)
    return info.get("required", []) if info else []


def get_recommended_properties(schema_type: str) -> list[str]:
    """Get recommended properties for a schema type."""
    info = GOOGLE_RICH_RESULT_TYPES.get(schema_type)
    return info.get("recommended", []) if info else []


# Schema.org vocabulary - known types (for "unknown type" detection)
# This is a subset of common types; in production you might load from schema.org
SCHEMA_ORG_KNOWN_TYPES: set[str] = {
    # Core types
    "Thing", "CreativeWork", "Article", "NewsArticle", "BlogPosting", "ScholarlyArticle",
    "Product", "Offer", "AggregateOffer", "LocalBusiness", "Organization", "Person",
    "Event", "JobPosting", "FAQPage", "Question", "Answer", "HowTo", "HowToStep",
    "Recipe", "BreadcrumbList", "ListItem", "VideoObject", "WebSite", "SearchAction",
    "Review", "AggregateRating", "Rating", "Course", "CourseInstance", "Dataset",
    "PodcastSeries", "PodcastEpisode", "SoftwareApplication", "Movie", "Book",
    "Place", "PostalAddress", "GeoCoordinates", "OpeningHoursSpecification",
    "ContactPoint", "Brand", "ImageObject", "MediaObject", "AudioObject",
    "MusicRecording", "MusicAlbum", "MusicGroup", "MusicPlaylist",
    "TVSeries", "TVEpisode", "TVSeason", "Clip", "Game", "VideoGame",
    "EducationalOccupationalProgram", "Occupation", "JobPosting",
    "Vehicle", "Car", "Bus", "Train", "Flight",
    "MedicalEntity", "MedicalCondition", "Drug", "Hospital", "Pharmacy",
    "GovernmentOrganization", "NGO", "Corporation", "EducationalOrganization",
    "SportsOrganization", "PerformingGroup", "Project", "ResearchProject",
    "FundingScheme", "Grant", "MonetaryAmount", "QuantitativeValue",
    "StructuredValue", "PropertyValue", "PropertyValueSpecification",
    "Action", "AchieveAction", "AssessAction", "ConsumeAction", "ControlAction",
    "CreateAction", "FindAction", "InteractAction", "MoveAction", "OrganizeAction",
    "PlayAction", "SearchAction", "TradeAction", "TransferAction", "UpdateAction",
    "WebPage", "WebPageElement", "SiteNavigationElement", "Table", "WPHeader",
    "WPFooter", "WPSideBar", "ItemPage", "CollectionPage", "ImageGallery",
    "VideoGallery", "Message", "EmailMessage", "SocialMediaPosting",
    "BlogPosting", "DiscussionForumPosting", "QAPage", "Comment",
    "UserInteraction", "UserLikes", "UserPlays", "UserShares", "UserCheckins",
    "UserTweets", "UserPlusOnes", "UserBlocks", "UserFollows", "UserReview",
    "UserDownloads", "UserPosts", "UserVisits", "UserViews", "UserMentions",
    "UserPurchases", "UserReservations", "UserRegistrations", "UserSubscriptions",
}


def is_known_schema_type(schema_type: str) -> bool:
    """Check if a schema type is known in Schema.org vocabulary."""
    return schema_type in SCHEMA_ORG_KNOWN_TYPES