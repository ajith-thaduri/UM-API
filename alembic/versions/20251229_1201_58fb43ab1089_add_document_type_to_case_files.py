"""add_document_type_to_case_files

Revision ID: 58fb43ab1089
Revises: 20251229_113707
Create Date: 2025-12-29 12:01:07.474737+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '58fb43ab1089'
down_revision: Union[str, None] = '20251229_113707'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add document_type column to case_files table
    op.add_column('case_files', sa.Column('document_type', sa.String(length=50), nullable=True))


def downgrade() -> None:
    # Remove document_type column from case_files table
    op.drop_column('case_files', 'document_type')
