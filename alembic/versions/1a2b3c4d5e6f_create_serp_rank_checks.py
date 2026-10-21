"""Create SERP rank check tables

Revision ID: 1a2b3c4d5e6f
Revises: 0bedd2ee713e
Create Date: 2026-10-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "1a2b3c4d5e6f"
down_revision: Union[str, Sequence[str], None] = "0bedd2ee713e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "serp_locations",
        sa.Column("location_code", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("country_iso", sa.Text(), nullable=True),
        sa.Column("location_type", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("location_code"),
    )
    op.create_table(
        "serp_languages",
        sa.Column("language_code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("language_code"),
    )
    op.create_table(
        "rank_checks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("keyword", sa.Text(), nullable=False),
        sa.Column("domain", sa.Text(), nullable=False),
        sa.Column(
            "location_code",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column("language_code", sa.Text(), nullable=False),
        sa.Column("device", sa.Text(), nullable=False),
        sa.Column("depth", sa.Integer(), nullable=False),
        sa.Column("include_preview", sa.Boolean(), nullable=False),
        sa.Column("fingerprint", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column(
            "provider_called_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column("provider_cost", sa.Numeric(10, 5), nullable=True),
        sa.Column("raw_response", postgresql.JSONB(), nullable=True),
        sa.Column("result", postgresql.JSONB(), nullable=True),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column("preview_status", sa.Text(), nullable=False),
        sa.Column("preview_html_url", sa.Text(), nullable=True),
        sa.Column("preview_image_url", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["location_code"],
            ["serp_locations.location_code"],
        ),
        sa.ForeignKeyConstraint(
            ["language_code"],
            ["serp_languages.language_code"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "device IN ('desktop','mobile')",
            name="ck_rank_checks_device",
        ),
        sa.CheckConstraint(
            "depth IN (10,20,50,100)",
            name="ck_rank_checks_depth",
        ),
    )
    op.create_index(
        "ix_rank_checks_user_created",
        "rank_checks",
        ["user_id", sa.text("created_at DESC")],
        unique=False,
    )
    op.create_index(
        "uq_rank_checks_inflight",
        "rank_checks",
        ["user_id", "fingerprint"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued','running')"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_rank_checks_inflight",
        table_name="rank_checks",
        postgresql_where=sa.text("status IN ('queued','running')"),
    )
    op.drop_index("ix_rank_checks_user_created", table_name="rank_checks")
    op.drop_table("rank_checks")
    op.drop_table("serp_languages")
    op.drop_table("serp_locations")
