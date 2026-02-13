"""Add Entity model and enhance EntitySource

Revision ID: page_rag_entities
Revises: page_rag_implementation
Create Date: 2026-02-11 11:55:00

Tables:
- entities: New table for grounded clinical facts
Updates:
- entity_sources: Update entity_id to FK (manual migration required if data exists)
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'page_rag_entities'
down_revision = 'page_rag_implementation'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Create entities table
    op.create_table(
        'entities',
        sa.Column('entity_id', sa.String(), nullable=False),
        sa.Column('case_id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('entity_type', sa.String(length=50), nullable=False),
        sa.Column('value', sa.Text(), nullable=False),
        sa.Column('normalized_value', sa.Text(), nullable=True),
        sa.Column('entity_date', sa.DateTime(), nullable=True),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('entity_metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['case_id'], ['cases.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('entity_id')
    )
    
    # Create indexes for entities
    op.create_index('ix_entities_case_id', 'entities', ['case_id'])
    op.create_index('ix_entities_entity_id', 'entities', ['entity_id'])
    op.create_index('ix_entities_entity_type', 'entities', ['entity_type'])
    op.create_index('ix_entities_user_id', 'entities', ['user_id'])
    op.create_index('ix_entities_entity_date', 'entities', ['entity_date'])
    op.create_index('idx_entity_type_date', 'entities', ['entity_type', 'entity_date'])
    op.create_index('idx_entity_normalized_value', 'entities', ['normalized_value'])
    op.create_index('idx_entity_case_type', 'entities', ['case_id', 'entity_type'])

    # 2. Add page_id to entity_sources (for precise grounding)
    op.add_column('entity_sources', sa.Column('page_id', sa.String(), nullable=True))
    op.create_foreign_key(
        'fk_entity_sources_page_id',
        'entity_sources',
        'normalized_pages',
        ['page_id'],
        ['page_id'],
        ondelete='CASCADE'
    )
    op.create_index('ix_entity_sources_page_id', 'entity_sources', ['page_id'])

    # Note: Adding FK constraint to entity_id in entity_sources is risky if data exists
    # and IDs don't match. Skipping strict FK for now, but application logic will enforce it.
    # Ideally:
    # op.create_foreign_key('fk_entity_sources_entity_id', 'entity_sources', 'entities', ['entity_id'], ['entity_id'], ondelete='CASCADE')


def downgrade():
    # Drop page_id from entity_sources
    op.drop_index('ix_entity_sources_page_id', table_name='entity_sources')
    op.drop_constraint('fk_entity_sources_page_id', 'entity_sources', type_='foreignkey')
    op.drop_column('entity_sources', 'page_id')

    # Drop entities table
    op.drop_index('idx_entity_case_type', table_name='entities')
    op.drop_index('idx_entity_normalized_value', table_name='entities')
    op.drop_index('idx_entity_type_date', table_name='entities')
    op.drop_index('ix_entities_entity_date', table_name='entities')
    op.drop_index('ix_entities_user_id', table_name='entities')
    op.drop_index('ix_entities_entity_type', table_name='entities')
    op.drop_index('ix_entities_entity_id', table_name='entities')
    op.drop_index('ix_entities_case_id', table_name='entities')
    op.drop_table('entities')
