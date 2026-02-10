"""add_conversation_messages_table

Revision ID: 9a46c12b7c1e
Revises: 20251230_180748
Create Date: 2025-12-31 09:23:16.407216+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9a46c12b7c1e'
down_revision: Union[str, None] = '20251230_180748'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create conversation_messages table
    op.create_table(
        'conversation_messages',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('case_id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('role', sa.String(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('sources', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['case_id'], ['cases.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes for optimized queries
    op.create_index(op.f('ix_conversation_messages_id'), 'conversation_messages', ['id'], unique=False)
    op.create_index(op.f('ix_conversation_messages_case_id'), 'conversation_messages', ['case_id'], unique=False)
    op.create_index(op.f('ix_conversation_messages_user_id'), 'conversation_messages', ['user_id'], unique=False)
    
    # Create composite indexes for efficient queries
    op.create_index('ix_conversation_case_user', 'conversation_messages', ['case_id', 'user_id'], unique=False)
    op.create_index('ix_conversation_case_created', 'conversation_messages', ['case_id', 'created_at'], unique=False)


def downgrade() -> None:
    # Drop indexes first
    op.drop_index('ix_conversation_case_created', table_name='conversation_messages')
    op.drop_index('ix_conversation_case_user', table_name='conversation_messages')
    op.drop_index(op.f('ix_conversation_messages_user_id'), table_name='conversation_messages')
    op.drop_index(op.f('ix_conversation_messages_case_id'), table_name='conversation_messages')
    op.drop_index(op.f('ix_conversation_messages_id'), table_name='conversation_messages')
    
    # Drop table
    op.drop_table('conversation_messages')
