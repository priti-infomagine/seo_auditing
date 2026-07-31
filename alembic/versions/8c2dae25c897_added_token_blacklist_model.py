"""added token blacklist model

Revision ID: 8c2dae25c897
Revises: 8d75447de444
Create Date: 2026-07-31 10:33:06.341981

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "8c2dae25c897"
down_revision: Union[str, Sequence[str], None] = "8d75447de444"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # Refresh token session information
    # ------------------------------------------------------------------
    op.add_column(
        "refresh_tokens",
        sa.Column("device_name", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "refresh_tokens",
        sa.Column("device_type", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "refresh_tokens",
        sa.Column("browser", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "refresh_tokens",
        sa.Column("os", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "refresh_tokens",
        sa.Column("ip_address", sa.String(length=45), nullable=True),
    )
    op.add_column(
        "refresh_tokens",
        sa.Column("user_agent", sa.String(length=1024), nullable=True),
    )
    op.add_column(
        "refresh_tokens",
        sa.Column(
            "last_used_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # ------------------------------------------------------------------
    # Token blacklist
    # ------------------------------------------------------------------
    op.create_table(
        "token_blacklist",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "jti",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "revoked_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "reason",
            sa.String(length=50),
            nullable=True,
        ),
        sa.UniqueConstraint("jti"),
    )

    op.create_index(
        "ix_token_blacklist_jti",
        "token_blacklist",
        ["jti"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_token_blacklist_jti",
        table_name="token_blacklist",
    )

    op.drop_table("token_blacklist")

    op.drop_column("refresh_tokens", "last_used_at")
    op.drop_column("refresh_tokens", "user_agent")
    op.drop_column("refresh_tokens", "ip_address")
    op.drop_column("refresh_tokens", "os")
    op.drop_column("refresh_tokens", "browser")
    op.drop_column("refresh_tokens", "device_type")
    op.drop_column("refresh_tokens", "device_name")