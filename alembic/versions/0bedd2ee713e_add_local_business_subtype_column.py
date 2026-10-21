"""Add local_business_subtype column to schema_generations

Revision ID: 0bedd2ee713e
Revises: f2a8c7d1e609
Create Date: 2026-10-12 11:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '0bedd2ee713e'
down_revision = 'f2a8c7d1e609'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add local_business_subtype column to schema_generations
    op.add_column(
        'schema_generations',
        sa.Column(
            'local_business_subtype',
            postgresql.ENUM(
                'restaurant', 'store', 'medical_business', 'professional_service',
                'automotive_business', 'child_care', 'dentist', 'dry_cleaning',
                'electrician', 'emergency_service', 'employment_agency',
                'entertainment_business', 'financial_service', 'food_establishment',
                'government_office', 'health_and_beauty_business',
                'home_and_construction_business', 'hvac_business',
                'insurance_agency', 'internet_cafe', 'legal_service',
                'library', 'lodging_business', 'medical_clinic', 'moving_company',
                'notary', 'optometrist', 'painter', 'pharmacy', 'physician',
                'plumber', 'police_station', 'real_estate_agent',
                'recycling_center', 'roofing_contractor', 'self_storage',
                'shopping_center', 'sports_activity_location',
                'travel_agency', 'veterinary_care',
                name='localbusinesssubtype',
                create_type=False
            ),
            nullable=True
        )
    )


def downgrade() -> None:
    # Remove local_business_subtype column
    op.drop_column('schema_generations', 'local_business_subtype')