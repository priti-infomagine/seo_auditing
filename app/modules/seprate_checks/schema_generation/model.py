import enum
import uuid

from sqlalchemy import Enum, Float, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin


class SchemaType(str, enum.Enum):
    ORGANIZATION = "organization"
    LOCAL_BUSINESS = "local_business"
    ARTICLE = "article"
    PRODUCT = "product"
    WEBSITE = "website"
    EVENT = "event"
    JOB_POSTING = "job_posting"
    FAQ_PAGE = "faq_page"
    HOW_TO = "how_to"


class ArticleSubType(str, enum.Enum):
    ARTICLE = "article"
    BLOG_POSTING = "blog_posting"
    NEWS_ARTICLE = "news_article"


class LocalBusinessSubType(str, enum.Enum):
    RESTAURANT = "restaurant"
    STORE = "store"
    MEDICAL_BUSINESS = "medical_business"
    PROFESSIONAL_SERVICE = "professional_service"
    AUTOMOTIVE_BUSINESS = "automotive_business"
    CHILD_CARE = "child_care"
    DENTIST = "dentist"
    DRY_CLEANING = "dry_cleaning"
    ELECTRICIAN = "electrician"
    EMERGENCY_SERVICE = "emergency_service"
    EMPLOYMENT_AGENCY = "employment_agency"
    ENTERTAINMENT_BUSINESS = "entertainment_business"
    FINANCIAL_SERVICE = "financial_service"
    FOOD_ESTABLISHMENT = "food_establishment"
    GOVERNMENT_OFFICE = "government_office"
    HEALTH_AND_BEAUTY_BUSINESS = "health_and_beauty_business"
    HOME_AND_CONSTRUCTION_BUSINESS = "home_and_construction_business"
    HVAC_BUSINESS = "hvac_business"
    INSURANCE_AGENCY = "insurance_agency"
    INTERNET_CAFE = "internet_cafe"
    LEGAL_SERVICE = "legal_service"
    LIBRARY = "library"
    LODGING_BUSINESS = "lodging_business"
    MEDICAL_CLINIC = "medical_clinic"
    MOVING_COMPANY = "moving_company"
    NOTARY = "notary"
    OPTOMETRIST = "optometrist"
    PAINTER = "painter"
    PHARMACY = "pharmacy"
    PHYSICIAN = "physician"
    PLUMBER = "plumber"
    POLICE_STATION = "police_station"
    REAL_ESTATE_AGENT = "real_estate_agent"
    RECYCLING_CENTER = "recycling_center"
    ROOFING_CONTRACTOR = "roofing_contractor"
    SELF_STORAGE = "self_storage"
    SHOPPING_CENTER = "shopping_center"
    SPORTS_ACTIVITY_LOCATION = "sports_activity_location"
    TRAVEL_AGENCY = "travel_agency"
    VETERINARY_CARE = "veterinary_care"


class EmploymentType(str, enum.Enum):
    FULL_TIME = "FULL_TIME"
    PART_TIME = "PART_TIME"
    CONTRACTOR = "CONTRACTOR"
    TEMPORARY = "TEMPORARY"
    INTERN = "INTERN"
    VOLUNTEER = "VOLUNTEER"
    PER_DIEM = "PER_DIEM"
    OTHER = "OTHER"


class EventStatus(str, enum.Enum):
    EVENT_SCHEDULED = "EventScheduled"
    EVENT_CANCELLED = "EventCancelled"
    EVENT_RESCHEDULED = "EventRescheduled"
    EVENT_POSTPONED = "EventPostponed"


class EventAttendanceMode(str, enum.Enum):
    OFFLINE = "OfflineEventAttendanceMode"
    ONLINE = "OnlineEventAttendanceMode"
    MIXED = "MixedEventAttendanceMode"


class GenerationStatus(str, enum.Enum):
    COMPLETED = "completed"
    FAILED = "failed"


class SchemaGeneration(TimestampMixin, Base):
    __tablename__ = "schema_generations"

    __table_args__ = (
        Index("ix_schema_generations_type_created", "schema_type", "created_at"),
        Index("ix_schema_generations_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    schema_type: Mapped[str] = mapped_column(
        Enum(SchemaType, name="schematype", create_type=False, validate_strings=True),
        nullable=False,
        index=True,
    )
    article_subtype: Mapped[str | None] = mapped_column(
        Enum(ArticleSubType, name="articlesubtype", create_type=False, validate_strings=True),
        nullable=True,
    )
    local_business_subtype: Mapped[str | None] = mapped_column(
        Enum(LocalBusinessSubType, name="localbusinesssubtype", create_type=False, validate_strings=True),
        nullable=True,
    )
    input_data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    generated_jsonld: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    warnings: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(
        Enum(GenerationStatus, name="generationstatus", create_type=False, validate_strings=True),
        nullable=False,
        default=GenerationStatus.COMPLETED.value,
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    cost_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    check_version: Mapped[str] = mapped_column(
        String(20), nullable=False, default="1.0.0"
    )


class SchemaAudit(TimestampMixin, Base):
    __tablename__ = "schema_audits"

    __table_args__ = (
        Index("ix_schema_audits_url_created", "url", "created_at"),
        Index("ix_schema_audits_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    url: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    detected_schemas: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="completed")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    cost_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    check_version: Mapped[str] = mapped_column(
        String(20), nullable=False, default="1.0.0"
    )