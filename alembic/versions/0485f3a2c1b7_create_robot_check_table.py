"""create robot_check table

Revision ID: 0485f3a2c1b7
Revises: bd44f7f79ef0
Create Date: 2026-09-23

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "0485f3a2c1b7"
down_revision: Union[str, Sequence[str], None] = "bd44f7f79ef0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "robot_check",
        sa.Column(
            "id",
            sa.UUID(),
            nullable=False,
        ),
        sa.Column(
            "domain",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "exists",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "status_code",
            sa.SmallInteger(),
            nullable=True,
        ),
        sa.Column(
            "fetch_status",
            sa.Enum("success", "not_found", "unreachable", name="fetchstatus"),
            nullable=False,
        ),
        sa.Column(
            "size_bytes",
            sa.Integer(),
            nullable=True,
        ),
        sa.Column(
            "raw_content",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "fetched_url",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "user_agent_groups",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "sitemaps_declared",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "sitemap_reachability",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "syntax_warnings",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "blocks_entire_site",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "blocks_assets",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "oversized",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "overall_status",
            sa.Enum(
                "pass", "warning", "fail", "not_applicable", name="overallstatus"
            ),
            nullable=False,
        ),
        sa.Column(
            "severity",
            sa.Enum(
                "none", "low", "medium", "high", "critical", name="severity"
            ),
            nullable=False,
        ),
        sa.Column(
            "evidence",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "why",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "recommendation",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "check_version",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'1.0.0'")),
        sa.PrimaryKeyConstraint(
            "id",
            name=op.f("robot_check_pkey"),
        ),
    )

    op.create_index(
        "ix_robot_check_domain",
        "robot_check",
        ["domain"],
        unique=False,
    )

    op.create_index(
        "ix_robot_check_domain_checked",
        "robot_check",
        ["domain", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "ix_robot_check_domain_checked",
        table_name="robot_check",
    )

    op.drop_index(
        "ix_robot_check_domain",
        table_name="robot_check",
    )

    op.drop_table("robot_check")

    sa.Enum(name="fetchstatus").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="overallstatus").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="severity").drop(op.get_bind(), checkfirst=True)
