"""Page-Indexed RAG implementation tables

Revision ID: page_rag_implementation
Revises: a030f3bad946
Create Date: 2026-02-11 11:40:00

Tables:
- normalized_pages
- page_vectors
- page_temporal_profiles
Updates:
- document_chunks (add page_id)
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import Vector


# revision identifiers, used by Alembic.
revision = 'page_rag_implementation'
down_revision = 'a030f3bad946'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Create normalized_pages
    op.create_table(
        'normalized_pages',
        sa.Column('page_id', sa.String(), nullable=False),
        sa.Column('case_id', sa.String(), nullable=False),
        sa.Column('file_id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('page_number', sa.Integer(), nullable=False),
        sa.Column('raw_text', sa.Text(), nullable=False),
        sa.Column('text_hash', sa.String(length=64), nullable=False),
        sa.Column('layout_tokens', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('char_count', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['case_id'], ['cases.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['file_id'], ['case_files.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('page_id')
    )
    
    op.create_index('ix_normalized_pages_case_id', 'normalized_pages', ['case_id'])
    op.create_index('ix_normalized_pages_file_id', 'normalized_pages', ['file_id'])
    op.create_index('ix_normalized_pages_page_id', 'normalized_pages', ['page_id'])
    op.create_index('ix_normalized_pages_user_id', 'normalized_pages', ['user_id'])
    op.create_index('idx_page_case_file', 'normalized_pages', ['case_id', 'file_id', 'page_number'])
    op.create_index('idx_page_text_hash', 'normalized_pages', ['text_hash'])
    op.create_index('idx_normalized_pages_case_user', 'normalized_pages', ['case_id', 'user_id'])

    # 2. Create page_vectors
    op.create_table(
        'page_vectors',
        sa.Column('page_id', sa.String(), nullable=False),
        sa.Column('case_id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('embedding', Vector(1536), nullable=False),
        sa.Column('entity_count', sa.Integer(), nullable=True),
        sa.Column('dated_entity_count', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['case_id'], ['cases.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['page_id'], ['normalized_pages.page_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('page_id')
    )
    
    op.create_index('ix_page_vectors_case_id', 'page_vectors', ['case_id'])
    op.create_index('ix_page_vectors_page_id', 'page_vectors', ['page_id'])
    op.create_index('ix_page_vectors_user_id', 'page_vectors', ['user_id'])
    op.create_index('idx_page_vectors_case_user', 'page_vectors', ['case_id', 'user_id'])
    
    # HNSW Index
    op.create_index(
        'idx_page_embedding_cosine',
        'page_vectors',
        ['embedding'],
        postgresql_using='hnsw',
        postgresql_with={'m': 16, 'ef_construction': 64},
        postgresql_ops={'embedding': 'vector_cosine_ops'}
    )

    # 3. Create page_temporal_profiles
    op.create_table(
        'page_temporal_profiles',
        sa.Column('page_id', sa.String(), nullable=False),
        sa.Column('earliest_entity_date', sa.DateTime(), nullable=True),
        sa.Column('latest_entity_date', sa.DateTime(), nullable=True),
        sa.Column('dated_entity_count', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['page_id'], ['normalized_pages.page_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('page_id')
    )
    
    op.create_index('ix_page_temporal_profiles_page_id', 'page_temporal_profiles', ['page_id'])
    op.create_index('idx_temporal_range', 'page_temporal_profiles', ['earliest_entity_date', 'latest_entity_date'])
    op.create_index('idx_temporal_earliest', 'page_temporal_profiles', ['earliest_entity_date'])
    op.create_index('idx_temporal_latest', 'page_temporal_profiles', ['latest_entity_date'])

    # 4. Add page_id to document_chunks
    op.add_column('document_chunks', sa.Column('page_id', sa.String(), nullable=True))
    op.create_foreign_key(
        'fk_document_chunks_page_id',
        'document_chunks',
        'normalized_pages',
        ['page_id'],
        ['page_id'],
        ondelete='CASCADE'
    )
    op.create_index('ix_document_chunks_page_id', 'document_chunks', ['page_id'])


def downgrade():
    # 4. Drop page_id from document_chunks
    op.drop_index('ix_document_chunks_page_id', table_name='document_chunks')
    op.drop_constraint('fk_document_chunks_page_id', 'document_chunks', type_='foreignkey')
    op.drop_column('document_chunks', 'page_id')

    # 3. Drop page_temporal_profiles
    op.drop_index('idx_temporal_latest', table_name='page_temporal_profiles')
    op.drop_index('idx_temporal_earliest', table_name='page_temporal_profiles')
    op.drop_index('idx_temporal_range', table_name='page_temporal_profiles')
    op.drop_index('ix_page_temporal_profiles_page_id', table_name='page_temporal_profiles')
    op.drop_table('page_temporal_profiles')

    # 2. Drop page_vectors
    op.drop_index('idx_page_embedding_cosine', table_name='page_vectors')
    op.drop_index('idx_page_vectors_case_user', table_name='page_vectors')
    op.drop_index('ix_page_vectors_user_id', table_name='page_vectors')
    op.drop_index('ix_page_vectors_page_id', table_name='page_vectors')
    op.drop_index('ix_page_vectors_case_id', table_name='page_vectors')
    op.drop_table('page_vectors')

    # 1. Drop normalized_pages
    op.drop_index('idx_normalized_pages_case_user', table_name='normalized_pages')
    op.drop_index('idx_page_text_hash', table_name='normalized_pages')
    op.drop_index('idx_page_case_file', table_name='normalized_pages')
    op.drop_index('ix_normalized_pages_user_id', table_name='normalized_pages')
    op.drop_index('ix_normalized_pages_page_id', table_name='normalized_pages')
    op.drop_index('ix_normalized_pages_file_id', table_name='normalized_pages')
    op.drop_index('ix_normalized_pages_case_id', table_name='normalized_pages')
    op.drop_table('normalized_pages')
