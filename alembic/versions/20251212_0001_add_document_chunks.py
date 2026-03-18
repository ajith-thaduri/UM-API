"""Add document chunks table for RAG

Revision ID: 20251212_0001
Revises: 20251211_0001
Create Date: 2025-12-12

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20251212_0001'
down_revision: Union[str, None] = '20251211_0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create document_chunks table
    op.create_table(
        'document_chunks',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('case_id', sa.String(), nullable=False),
        sa.Column('file_id', sa.String(), nullable=False),
        sa.Column('chunk_index', sa.Integer(), nullable=False),
        sa.Column('page_number', sa.Integer(), nullable=False),
        sa.Column('section_type', sa.Enum(
            'medications', 'labs', 'diagnoses', 'procedures', 'vitals',
            'imaging', 'allergies', 'history', 'assessment', 'plan',
            'narrative', 'chief_complaint', 'physical_exam', 'discharge', 'unknown',
            name='sectiontype'
        ), nullable=False),
        sa.Column('chunk_text', sa.Text(), nullable=False),
        sa.Column('char_start', sa.Integer(), nullable=False),
        sa.Column('char_end', sa.Integer(), nullable=False),
        sa.Column('token_count', sa.Integer(), nullable=False),
        sa.Column('pinecone_id', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['case_id'], ['cases.id'], ),
        sa.ForeignKeyConstraint(['file_id'], ['case_files.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes
    op.create_index(op.f('ix_document_chunks_id'), 'document_chunks', ['id'], unique=False)
    op.create_index(op.f('ix_document_chunks_case_id'), 'document_chunks', ['case_id'], unique=False)
    op.create_index(op.f('ix_document_chunks_file_id'), 'document_chunks', ['file_id'], unique=False)
    op.create_index(op.f('ix_document_chunks_pinecone_id'), 'document_chunks', ['pinecone_id'], unique=True)
    
    # Add chunk_id to source_links table for chunk-based source linking
    op.add_column('source_links', sa.Column('chunk_id', sa.String(), nullable=True))
    op.create_index(op.f('ix_source_links_chunk_id'), 'source_links', ['chunk_id'], unique=False)


def downgrade() -> None:
    # Remove chunk_id from source_links
    op.drop_index(op.f('ix_source_links_chunk_id'), table_name='source_links')
    op.drop_column('source_links', 'chunk_id')
    
    # Drop document_chunks table
    op.drop_index(op.f('ix_document_chunks_pinecone_id'), table_name='document_chunks')
    op.drop_index(op.f('ix_document_chunks_file_id'), table_name='document_chunks')
    op.drop_index(op.f('ix_document_chunks_case_id'), table_name='document_chunks')
    op.drop_index(op.f('ix_document_chunks_id'), table_name='document_chunks')
    op.drop_table('document_chunks')
    
    # Drop the enum type
    op.execute('DROP TYPE IF EXISTS sectiontype')

