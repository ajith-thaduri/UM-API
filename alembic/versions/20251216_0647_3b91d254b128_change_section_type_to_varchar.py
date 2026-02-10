"""change_section_type_to_varchar

Revision ID: 3b91d254b128
Revises: 20251212_0001
Create Date: 2025-12-16 06:47:08.042155+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3b91d254b128'
down_revision: Union[str, None] = '20251212_0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Change section_type from enum to VARCHAR to avoid enum value mismatches
    # First, alter the column type
    op.execute("""
        ALTER TABLE document_chunks 
        ALTER COLUMN section_type TYPE VARCHAR(50) 
        USING section_type::text
    """)
    
    # Drop the enum type (optional, but cleans up)
    op.execute('DROP TYPE IF EXISTS sectiontype')


def downgrade() -> None:
    # Recreate the enum type
    op.execute("""
        CREATE TYPE sectiontype AS ENUM (
            'medications', 'labs', 'diagnoses', 'procedures', 'vitals',
            'imaging', 'allergies', 'history', 'assessment', 'plan',
            'narrative', 'chief_complaint', 'physical_exam', 'discharge', 'unknown'
        )
    """)
    
    # Change column back to enum
    op.execute("""
        ALTER TABLE document_chunks 
        ALTER COLUMN section_type TYPE sectiontype 
        USING section_type::sectiontype
    """)
