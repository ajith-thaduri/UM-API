"""enable_pgvector

Revision ID: 1c24b179236c
Revises: 9db681381b4b
Create Date: 2026-01-09 08:47:11.718686+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1c24b179236c'
down_revision: Union[str, None] = '9db681381b4b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create pgvector extension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    
    # Add embedding column
    # We use explicit SQL or sqlalchemy type. Using explicit vector type requires importing pgvector.
    # To avoid dependency in migration file if possible, we can use sa.Column('embedding', Vector(1536))
    
    from pgvector.sqlalchemy import Vector
    op.add_column('document_chunks', sa.Column('embedding', Vector(1536), nullable=True))
    
    # Create HNSW index for performance
    # Index name: idx_embedding_cosine
    op.create_index(
        'idx_embedding_cosine',
        'document_chunks',
        ['embedding'],
        postgresql_using='hnsw',
        postgresql_ops={'embedding': 'vector_cosine_ops'}
    )


def downgrade() -> None:
    op.drop_index('idx_embedding_cosine', table_name='document_chunks')
    op.drop_column('document_chunks', 'embedding')
    # We don't drop the extension usually as other tables might use it, but here we can
    op.execute("DROP EXTENSION IF EXISTS vector")
