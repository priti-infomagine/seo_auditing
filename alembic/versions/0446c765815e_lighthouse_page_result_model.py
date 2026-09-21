
"""lighthouse page result model

Revision ID: 0446c765815e
Revises: 64acf8cf44e5
Create Date: 2026-09-19 11:17:11.832115
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "0446c765815e"
down_revision: Union[str, Sequence[str], None] = "64acf8cf44e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.create_table(
        "lighthouse_page_results",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "check_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "domain",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column(
            "url",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "device",
            sa.Enum(
                "MOBILE",
                "DESKTOP",
                name="device",
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "SUCCESS",
                "FAILED",
                "SKIPPED",
                name="pagestatus",
            ),
            nullable=False,
        ),
        sa.Column(
            "reason",
            sa.String(length=255),
            nullable=True,
        ),
        sa.Column(
            "performance_score",
            sa.Integer(),
            nullable=True,
        ),
        sa.Column(
            "seo_score",
            sa.Integer(),
            nullable=True,
        ),
        sa.Column(
            "fcp_ms",
            sa.Integer(),
            nullable=True,
        ),
        sa.Column(
            "lcp_ms",
            sa.Integer(),
            nullable=True,
        ),
        sa.Column(
            "tbt_ms",
            sa.Integer(),
            nullable=True,
        ),
        sa.Column(
            "cls",
            sa.Float(),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint(
            "id",
            name=op.f("lighthouse_page_results_pkey"),
        ),
        sa.UniqueConstraint(
            "check_id",
            "url",
            "device",
            name="uq_check_url_device",
        ),
    )

    op.create_index(
        "ix_lighthouse_check_id",
        "lighthouse_page_results",
        ["check_id"],
        unique=False,
    )

    op.create_index(
        "ix_lighthouse_domain_created",
        "lighthouse_page_results",
        ["domain", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_index(
        "ix_lighthouse_domain_created",
        table_name="lighthouse_page_results",
    )

    op.drop_index(
        "ix_lighthouse_check_id",
        table_name="lighthouse_page_results",
    )

    op.drop_table("lighthouse_page_results")

    # Drop the PostgreSQL enum types created for this table.
    sa.Enum(
        "SUCCESS",
        "FAILED",
        "SKIPPED",
        name="pagestatus",
    ).drop(op.get_bind(), checkfirst=True)

    sa.Enum(
        "MOBILE",
        "DESKTOP",
        name="device",
    ).drop(op.get_bind(), checkfirst=True)