"""Add tier columns to user_preferences

Revision ID: 20260213_1305
Revises: af60f5f9a477
Create Date: 2026-02-13 13:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260213_1305'
down_revision: Union[str, None] = 'af60f5f9a477'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add tier columns to user_preferences
    op.add_column('user_preferences', sa.Column('tier1_model', sa.String(), nullable=True))
    op.add_column('user_preferences', sa.Column('tier2_model', sa.String(), nullable=True))
    
    # Add presidio_enabled with default True
    # We use server_default to populate existing rows, then we can drop it if needed or keep it
    op.add_column('user_preferences', sa.Column('presidio_enabled', sa.Boolean(), server_default='true', nullable=False))


def downgrade() -> None:
    # Drop columns
    op.drop_column('user_preferences', 'presidio_enabled')
    op.drop_column('user_preferences', 'tier2_model')
    op.drop_column('user_preferences', 'tier1_model')
