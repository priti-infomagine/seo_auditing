"""add url to sitemap_checks

Revision ID: 3807b3c21605
Revises: 0a1b2c3d4e5f
Create Date: 2026-09-26 11:41:47.477960

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3807b3c21605'
down_revision: Union[str, Sequence[str], None] = '0a1b2c3d4e5f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "sitemap_checks" in inspector.get_table_names():
        cols = {c["name"] for c in inspector.get_columns("sitemap_checks")}
        if "url" in cols:
            op.alter_column('sitemap_checks', 'url',
                       existing_type=sa.VARCHAR(),
                       type_=sa.Text(),
                       existing_nullable=False)
        if "robots_status_code" in cols:
            op.alter_column('sitemap_checks', 'robots_status_code',
                       existing_type=sa.SMALLINT(),
                       type_=sa.Integer(),
                       existing_nullable=True)


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "sitemap_checks" in inspector.get_table_names():
        cols = {c["name"] for c in inspector.get_columns("sitemap_checks")}
        if "robots_status_code" in cols:
            op.alter_column('sitemap_checks', 'robots_status_code',
                       existing_type=sa.Integer(),
                       type_=sa.SMALLINT(),
                       existing_nullable=True)
        if "url" in cols:
            op.alter_column('sitemap_checks', 'url',
                       existing_type=sa.Text(),
                       type_=sa.VARCHAR(),
                       existing_nullable=False)
