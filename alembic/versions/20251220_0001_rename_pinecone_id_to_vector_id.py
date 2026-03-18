"""Rename pinecone_id to vector_id in document_chunks

Revision ID: 20251220_0001
Revises: 8d9808b189d4
Create Date: 2025-12-20

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20251220_0001'
down_revision: Union[str, None] = '8d9808b189d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Rename pinecone_id column to vector_id
    op.alter_column('document_chunks', 'pinecone_id', new_column_name='vector_id', existing_type=sa.String(), existing_nullable=False)
    
    # Rename the index
    op.drop_index(op.f('ix_document_chunks_pinecone_id'), table_name='document_chunks')
    op.create_index(op.f('ix_document_chunks_vector_id'), 'document_chunks', ['vector_id'], unique=True)


def downgrade() -> None:
    # Rename vector_id column back to pinecone_id
    op.alter_column('document_chunks', 'vector_id', new_column_name='pinecone_id', existing_type=sa.String(), existing_nullable=False)
    
    # Rename the index back
    op.drop_index(op.f('ix_document_chunks_vector_id'), table_name='document_chunks')
    op.create_index(op.f('ix_document_chunks_pinecone_id'), 'document_chunks', ['pinecone_id'], unique=True)

