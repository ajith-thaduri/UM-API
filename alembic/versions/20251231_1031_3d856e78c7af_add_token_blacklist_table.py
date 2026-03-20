"""add_token_blacklist_table

Revision ID: 3d856e78c7af
Revises: 9a46c12b7c1e
Create Date: 2025-12-31 10:31:18.791746+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3d856e78c7af'
down_revision: Union[str, None] = '9a46c12b7c1e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create token_blacklist table
    op.create_table(
        'token_blacklist',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('token_hash', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('blacklisted_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes for optimized queries
    op.create_index(op.f('ix_token_blacklist_id'), 'token_blacklist', ['id'], unique=False)
    op.create_index(op.f('ix_token_blacklist_token_hash'), 'token_blacklist', ['token_hash'], unique=True)
    op.create_index(op.f('ix_token_blacklist_user_id'), 'token_blacklist', ['user_id'], unique=False)
    op.create_index(op.f('ix_token_blacklist_expires_at'), 'token_blacklist', ['expires_at'], unique=False)
    
    # Create composite indexes for efficient queries
    op.create_index('idx_blacklist_token_hash', 'token_blacklist', ['token_hash'], unique=False)
    op.create_index('idx_blacklist_expires_at', 'token_blacklist', ['expires_at'], unique=False)


def downgrade() -> None:
    # Drop indexes first
    op.drop_index('idx_blacklist_expires_at', table_name='token_blacklist')
    op.drop_index('idx_blacklist_token_hash', table_name='token_blacklist')
    op.drop_index(op.f('ix_token_blacklist_expires_at'), table_name='token_blacklist')
    op.drop_index(op.f('ix_token_blacklist_user_id'), table_name='token_blacklist')
    op.drop_index(op.f('ix_token_blacklist_token_hash'), table_name='token_blacklist')
    op.drop_index(op.f('ix_token_blacklist_id'), table_name='token_blacklist')
    
    # Drop table
    op.drop_table('token_blacklist')
