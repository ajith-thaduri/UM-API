"""Add word_segments to document_chunks for precise PDF term highlighting.

word_segments stores word-level bbox data for each chunk so that at query time
we can locate the exact bounding box of any extracted term (instead of the coarse
chunk-union bbox).

Format stored per chunk:
  [{"text": "Metformin", "bbox": {"x0": 100, "y0": 200, "x1": 160, "y1": 215}}, ...]

Revision ID: 20260305_1200
Revises: presidio_vault_hardening_20260304
Create Date: 2026-03-05 12:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260305_1200"
down_revision: Union[str, None] = "vault_hardening_v1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "document_chunks",
        sa.Column(
            "word_segments",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="Word-level [{text, bbox}] segments for precise term highlighting",
        ),
    )


def downgrade() -> None:
    op.drop_column("document_chunks", "word_segments")
