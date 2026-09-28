"""Standalone link analysis check DB models.

Two tables:
- ``link_analysis_checks`` — the task master row (one per job). Holds scalar
  aggregate columns and small JSONB summaries.
- ``link_findings`` — the per-finding rows. Each row records a single
  finding (issue or opportunity) with target URL, status code, evidence
  JSONB, and recommendation JSONB.

Redis is used for **status / progress** polling during async task execution
(ephemeral — populated by the Celery worker and read by the API router
via ``GET /check/{check_id}``).
"""
import enum
import uuid

from sqlalchemy import (
    Boolean,
    Enum,
    Float,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin


class LinkAnalysisCheckStatus(str, enum.Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class LinkAnalysisOverallStatus(str, enum.Enum):
    PASS = "pass"
    WARNING = "warning"
    FAIL = "fail"
    NOT_APPLICABLE = "not_applicable"


class LinkAnalysisSeverity(str, enum.Enum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class FindingCategory(str, enum.Enum):
    STANDARD = "standard"
    OPTIMIZATION = "optimization"


class FindingType(str, enum.Enum):
    BROKEN_INTERNAL = "broken_internal"
    BROKEN_EXTERNAL = "broken_external"
    REDIRECT_INTERNAL = "redirect_internal"
    REDIRECT_EXTERNAL = "redirect_external"
    ORPHAN = "orphan"
    SITEMAP_URL_ERROR = "sitemap_url_error"
    DEEP_PAGE = "deep_page"
    DEAD_END_PAGE = "dead_end_page"
    WEAKLY_LINKED_PAGE = "weakly_linked_page"
    EMPTY_ANCHOR = "empty_anchor"
    GENERIC_ANCHOR = "generic_anchor"
    NOFOLLOW_INTERNAL = "nofollow_internal"
    INSECURE_LINK = "insecure_link"
    EXCESSIVE_OUTLINKS = "excessive_outlinks"


class LinkStatusClass(str, enum.Enum):
    OK = "ok"
    REDIRECT = "redirect"
    BROKEN = "broken"
    UNVERIFIED = "unverified"


class WhereToFix(str, enum.Enum):
    SOURCE_PAGES = "source_pages"
    SERVER_CONFIG = "server_config"
    SITEMAP = "sitemap"
    CONTENT = "content"


class LinkAnalysisCheck(TimestampMixin, Base):
    """Persisted link-analysis task master row.

    The heavy per-finding data lives in the ``link_findings`` child table so
    that results can be streamed/paginated efficiently.  Summary aggregates
    and overall verdicts are cached on this row for quick retrieval.
    """

    __tablename__ = "link_analysis_checks"

    __table_args__ = (
        Index("ix_link_analysis_checks_domain_created", "domain", "created_at"),
        Index("ix_link_analysis_checks_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    domain: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default=LinkAnalysisCheckStatus.QUEUED.value
    )
    task_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    progress: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    summary: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    pages_crawled: Mapped[int | None] = mapped_column(nullable=True)
    crawl_truncated: Mapped[bool] = mapped_column(nullable=False, server_default="false")

    overall_status: Mapped[LinkAnalysisOverallStatus | None] = mapped_column(
        Enum(
            LinkAnalysisOverallStatus,
            name="link_analysis_overall_status",
            create_type=False,
            validate_strings=True,
        ),
        nullable=True,
    )
    severity: Mapped[LinkAnalysisSeverity | None] = mapped_column(
        Enum(
            LinkAnalysisSeverity,
            name="link_analysis_severity",
            create_type=False,
            validate_strings=True,
        ),
        nullable=True,
    )
    cost_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)

    check_version: Mapped[str] = mapped_column(
        String(20), nullable=False, default="1.0.0"
    )


class LinkFinding(TimestampMixin, Base):
    """Individual link finding row — one per finding (grouped by target URL).

    Stores per-finding detail so callers can paginate the full finding set
    without loading a monolithic JSONB blob.
    """

    __tablename__ = "link_findings"

    __table_args__ = (
        Index("ix_link_findings_check_category_type", "check_id", "category", "type"),
        Index("ix_link_findings_target", "target_url"),
        Index("ix_link_findings_severity", "severity"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    check_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("link_analysis_checks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    category: Mapped[str] = mapped_column(
        String(20), nullable=False, default=FindingCategory.STANDARD.value
    )
    type: Mapped[str] = mapped_column(String(50), nullable=False)

    severity: Mapped[str] = mapped_column(
        String(20), nullable=False, default=LinkAnalysisSeverity.LOW.value
    )

    target_url: Mapped[str] = mapped_column(Text, nullable=False, index=True)

    status_code: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    final_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    evidence: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    recommendation: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # TimestampMixin provides created_at and updated_at


__all__ = [
    "LinkAnalysisCheckStatus",
    "LinkAnalysisOverallStatus",
    "LinkAnalysisSeverity",
    "FindingCategory",
    "FindingType",
    "LinkStatusClass",
    "WhereToFix",
    "LinkAnalysisCheck",
    "LinkFinding",
]
