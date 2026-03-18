"""Add bbox field to document_chunks for PDF coordinate-based highlighting

Revision ID: 20251222_1539
Revises: 20251220_0001
Create Date: 2025-12-22 15:39:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '20251222_1539'
down_revision: Union[str, None] = '20251220_0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add bbox JSONB column to document_chunks
    # This stores bounding box coordinates for precise PDF highlighting
    # Format: {"x0": float, "y0": float, "x1": float, "y1": float}
    op.add_column('document_chunks', sa.Column('bbox', postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    # Remove bbox column
    op.drop_column('document_chunks', 'bbox')


