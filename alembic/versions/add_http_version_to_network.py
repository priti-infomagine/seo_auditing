"""Add http_version column to page_network_data

Revision ID: add_http_version_to_network
Revises: fd28ca5c536b
Create Date: 2026-11-17 11:32:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "add_http_version_to_network"
down_revision = "fd28ca5c536b"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "page_network_data",
        sa.Column("http_version", sa.String(20), nullable=True),
    )


def downgrade():
    op.drop_column("page_network_data", "http_version")