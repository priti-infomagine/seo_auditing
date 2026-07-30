"""add otp_type enum

Revision ID: 8d75447de444
Revises: a788b9e2d2da
Create Date: 2026-07-30 10:17:59.858486

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "8d75447de444"
down_revision: Union[str, Sequence[str], None] = "a788b9e2d2da"
branch_labels = None
depends_on = None


otp_type_enum = sa.Enum(
    "register_otp",
    "forgot_pass_otp",
    "reset_pass_otp",
    name="otp_type_enum",
)


def upgrade() -> None:
    bind = op.get_bind()

    # Create PostgreSQL enum type
    otp_type_enum.create(bind, checkfirst=True)

    # Add column
    op.add_column(
        "otps",
        sa.Column(
            "otp_type",
            otp_type_enum,
            nullable=False,
            server_default="register_otp",
        ),
    )

    # Remove default after existing rows are populated
    op.alter_column(
        "otps",
        "otp_type",
        server_default=None,
    )


def downgrade() -> None:
    op.drop_column("otps", "otp_type")

    bind = op.get_bind()
    otp_type_enum.drop(bind, checkfirst=True)