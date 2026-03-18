"""add executive_summary to clinical_extractions

Revision ID: f7a8b9c0d1e2
Revises: 42dd259e3d27
Create Date: 2026-01-23 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f7a8b9c0d1e2'
down_revision = '42dd259e3d27'
branch_labels = None
depends_on = None


def upgrade():
    """Add executive_summary column to clinical_extractions table."""
    op.add_column('clinical_extractions', 
        sa.Column('executive_summary', sa.Text(), nullable=True))


def downgrade():
    """Remove executive_summary column from clinical_extractions table."""
    op.drop_column('clinical_extractions', 'executive_summary')
