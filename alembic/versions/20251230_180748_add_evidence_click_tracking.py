"""add_evidence_click_tracking

Revision ID: 20251230_180748
Revises: 58fb43ab1089
Create Date: 2025-12-30 18:07:48.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20251230_180748'
down_revision: Union[str, None] = '58fb43ab1089'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create evidence_clicks table
    op.create_table(
        'evidence_clicks',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('case_id', sa.String(), nullable=False),
        sa.Column('entity_type', sa.String(), nullable=False),
        sa.Column('entity_id', sa.String(), nullable=False),
        sa.Column('source_type', sa.String(), nullable=False),
        sa.Column('file_id', sa.String(), nullable=True),
        sa.Column('page_number', sa.Integer(), nullable=True),
        sa.Column('chunk_id', sa.String(), nullable=True),
        sa.Column('clicked_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['case_id'], ['cases.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes for optimized queries
    op.create_index(op.f('ix_evidence_clicks_id'), 'evidence_clicks', ['id'], unique=False)
    op.create_index(op.f('ix_evidence_clicks_user_id'), 'evidence_clicks', ['user_id'], unique=False)
    op.create_index(op.f('ix_evidence_clicks_case_id'), 'evidence_clicks', ['case_id'], unique=False)
    op.create_index(op.f('ix_evidence_clicks_entity_type'), 'evidence_clicks', ['entity_type'], unique=False)
    op.create_index(op.f('ix_evidence_clicks_clicked_at'), 'evidence_clicks', ['clicked_at'], unique=False)
    
    # Create composite indexes for analytics queries
    op.create_index('idx_user_case_clicked', 'evidence_clicks', ['user_id', 'case_id', 'clicked_at'], unique=False)
    op.create_index('idx_user_entity_type', 'evidence_clicks', ['user_id', 'entity_type', 'clicked_at'], unique=False)
    op.create_index('idx_case_clicked', 'evidence_clicks', ['case_id', 'clicked_at'], unique=False)
    op.create_index('idx_user_clicked', 'evidence_clicks', ['user_id', 'clicked_at'], unique=False)


def downgrade() -> None:
    # Drop indexes first
    op.drop_index('idx_user_clicked', table_name='evidence_clicks')
    op.drop_index('idx_case_clicked', table_name='evidence_clicks')
    op.drop_index('idx_user_entity_type', table_name='evidence_clicks')
    op.drop_index('idx_user_case_clicked', table_name='evidence_clicks')
    op.drop_index(op.f('ix_evidence_clicks_clicked_at'), table_name='evidence_clicks')
    op.drop_index(op.f('ix_evidence_clicks_entity_type'), table_name='evidence_clicks')
    op.drop_index(op.f('ix_evidence_clicks_case_id'), table_name='evidence_clicks')
    op.drop_index(op.f('ix_evidence_clicks_user_id'), table_name='evidence_clicks')
    op.drop_index(op.f('ix_evidence_clicks_id'), table_name='evidence_clicks')
    
    # Drop table
    op.drop_table('evidence_clicks')

