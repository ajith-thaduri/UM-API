"""change_facet_type_to_varchar

Revision ID: 78e3506cde0f
Revises: 9fe96edf8950
Create Date: 2025-12-16 07:02:54.356729+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '78e3506cde0f'
down_revision: Union[str, None] = '9fe96edf8950'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Change facet_type from enum to VARCHAR to avoid enum value mismatches
    op.execute("""
        ALTER TABLE facet_results 
        ALTER COLUMN facet_type TYPE VARCHAR(50) 
        USING facet_type::text
    """)
    
    # Drop the enum type (optional, but cleans up)
    op.execute('DROP TYPE IF EXISTS facettype')


def downgrade() -> None:
    # Recreate the enum type
    op.execute("""
        CREATE TYPE facettype AS ENUM (
            'summary', 'clinical', 'timeline', 'red_flags', 'contradictions'
        )
    """)
    
    # Change column back to enum
    op.execute("""
        ALTER TABLE facet_results 
        ALTER COLUMN facet_type TYPE facettype 
        USING facet_type::facettype
    """)
