"""add timeline_summary column to clinical_extractions

Revision ID: 20251229_113707
Revises: 20251226_164659
Create Date: 2025-12-29 11:37:07
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20251229_113707"
down_revision = "20251226_164659"  # Matches revision ID from entity_sources migration
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add timeline_summary column to clinical_extractions table
    op.add_column('clinical_extractions', 
                  sa.Column('timeline_summary', postgresql.JSON(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    op.drop_column('clinical_extractions', 'timeline_summary')

