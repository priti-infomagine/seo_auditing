"""add crawl_config_recovered to crawl_jobs

Revision ID: 2bc9883146d0
Revises: 6065450519c4
Create Date: 2026-09-10 16:36:14.432684

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2bc9883146d0'
down_revision: Union[str, Sequence[str], None] = '6065450519c4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "crawl_jobs",
        sa.Column(
            "crawl_config_recovered",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("crawl_jobs", "crawl_config_recovered")
