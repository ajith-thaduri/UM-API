"""add entity_sources table for industry-standard source linking

Revision ID: 20251226_164659
Revises: 20251223_1504_add_wallet_system
Create Date: 2025-12-26 16:46:59
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20251226_164659"
down_revision = "20251223_1504"  # Matches revision ID from wallet_system migration
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create entity_sources table
    op.create_table(
        "entity_sources",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("case_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("entity_type", sa.String(length=50), nullable=False),  # 'medication', 'lab', 'timeline', etc.
        sa.Column("entity_id", sa.String(length=255), nullable=False),  # 'medication:0', 'timeline:abc123', etc.
        sa.Column("chunk_id", sa.String(), nullable=True),  # Reference to document_chunks
        sa.Column("file_id", sa.String(), nullable=True),  # Reference to case_files
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("bbox", postgresql.JSONB, nullable=True),  # {x0, y0, x1, y1} for precise highlighting
        sa.Column("snippet", sa.Text(), nullable=True),  # Exact text from chunk
        sa.Column("full_text", sa.Text(), nullable=True),  # Full page text if available
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("case_id", "entity_type", "entity_id", name="uq_entity_source"),
    )
    
    # Create indexes for fast lookups
    op.create_index("ix_entity_sources_case_id", "entity_sources", ["case_id"])
    op.create_index("ix_entity_sources_entity", "entity_sources", ["entity_type", "entity_id"])
    op.create_index("ix_entity_sources_chunk_id", "entity_sources", ["chunk_id"])
    op.create_index("ix_entity_sources_file_id", "entity_sources", ["file_id"])
    op.create_index("ix_entity_sources_user_id", "entity_sources", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_entity_sources_user_id", table_name="entity_sources")
    op.drop_index("ix_entity_sources_file_id", table_name="entity_sources")
    op.drop_index("ix_entity_sources_chunk_id", table_name="entity_sources")
    op.drop_index("ix_entity_sources_entity", table_name="entity_sources")
    op.drop_index("ix_entity_sources_case_id", table_name="entity_sources")
    op.drop_table("entity_sources")

