"""Add revision impact, confidence summary, and merge context for versioned summaries.

Revision ID: case_version_revision_artifacts
Revises: conv_msg_case_version
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "case_version_revision_artifacts"
down_revision: Union[str, None] = "conv_msg_case_version"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "case_versions",
        sa.Column("revision_impact_report", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "case_versions",
        sa.Column("confidence_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "case_versions",
        sa.Column("review_flags", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column("case_versions", sa.Column("materiality_label", sa.String(length=64), nullable=True))
    op.add_column(
        "clinical_extractions",
        sa.Column("version_merge_context", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("clinical_extractions", "version_merge_context")
    op.drop_column("case_versions", "materiality_label")
    op.drop_column("case_versions", "review_flags")
    op.drop_column("case_versions", "confidence_summary")
    op.drop_column("case_versions", "revision_impact_report")
