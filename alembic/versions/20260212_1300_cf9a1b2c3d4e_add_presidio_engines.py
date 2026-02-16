"""Add presidio_engines table

Revision ID: cf9a1b2c3d4e
Revises: b2257e8a37ea
Create Date: 2026-02-12 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'cf9a1b2c3d4e'
down_revision: Union[str, None] = 'b2257e8a37ea'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # Create presidio_engines table
    op.create_table('presidio_engines',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('description', sa.String(), nullable=True),
        sa.Column('engine_type', sa.String(), nullable=False),
        sa.Column('model_name', sa.String(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('config', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_presidio_engines_name'), 'presidio_engines', ['name'], unique=True)

def downgrade() -> None:
    op.drop_index(op.f('ix_presidio_engines_name'), table_name='presidio_engines')
    op.drop_table('presidio_engines')
