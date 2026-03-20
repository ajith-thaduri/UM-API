"""Add usage_metrics table for tracking LLM token usage

Revision ID: 20251223_1216
Revises: 20251223_1215
Create Date: 2025-12-23 12:16:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '20251223_1216'
down_revision: Union[str, None] = '20251223_1215'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create usage_metrics table
    op.create_table(
        'usage_metrics',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('case_id', sa.String(), nullable=True),
        sa.Column('provider', sa.String(), nullable=False),
        sa.Column('model', sa.String(), nullable=False),
        sa.Column('operation_type', sa.String(), nullable=False),
        sa.Column('prompt_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('completion_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('estimated_cost_usd', sa.Numeric(precision=10, scale=6), nullable=True),
        sa.Column('request_timestamp', sa.DateTime(), nullable=False),
        sa.Column('extra_metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['case_id'], ['cases.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes
    op.create_index(op.f('ix_usage_metrics_id'), 'usage_metrics', ['id'], unique=False)
    op.create_index(op.f('ix_usage_metrics_user_id'), 'usage_metrics', ['user_id'], unique=False)
    op.create_index(op.f('ix_usage_metrics_case_id'), 'usage_metrics', ['case_id'], unique=False)
    op.create_index(op.f('ix_usage_metrics_provider'), 'usage_metrics', ['provider'], unique=False)
    op.create_index(op.f('ix_usage_metrics_model'), 'usage_metrics', ['model'], unique=False)
    op.create_index(op.f('ix_usage_metrics_operation_type'), 'usage_metrics', ['operation_type'], unique=False)
    op.create_index(op.f('ix_usage_metrics_request_timestamp'), 'usage_metrics', ['request_timestamp'], unique=False)
    
    # Create composite indexes for common queries
    op.create_index('idx_user_timestamp', 'usage_metrics', ['user_id', 'request_timestamp'], unique=False)
    op.create_index('idx_provider_model', 'usage_metrics', ['provider', 'model'], unique=False)
    op.create_index('idx_case_operation', 'usage_metrics', ['case_id', 'operation_type'], unique=False)


def downgrade() -> None:
    # Drop composite indexes
    op.drop_index('idx_case_operation', table_name='usage_metrics')
    op.drop_index('idx_provider_model', table_name='usage_metrics')
    op.drop_index('idx_user_timestamp', table_name='usage_metrics')
    
    # Drop single column indexes
    op.drop_index(op.f('ix_usage_metrics_request_timestamp'), table_name='usage_metrics')
    op.drop_index(op.f('ix_usage_metrics_operation_type'), table_name='usage_metrics')
    op.drop_index(op.f('ix_usage_metrics_model'), table_name='usage_metrics')
    op.drop_index(op.f('ix_usage_metrics_provider'), table_name='usage_metrics')
    op.drop_index(op.f('ix_usage_metrics_case_id'), table_name='usage_metrics')
    op.drop_index(op.f('ix_usage_metrics_user_id'), table_name='usage_metrics')
    op.drop_index(op.f('ix_usage_metrics_id'), table_name='usage_metrics')
    
    # Drop table
    op.drop_table('usage_metrics')

