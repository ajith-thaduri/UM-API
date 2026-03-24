"""Phase 2: case vault tracking, version processing metadata, merge artifacts.

Revision ID: phase2_case_vault_merge
Revises: case_version_revision_artifacts
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "phase2_case_vault_merge"
down_revision: Union[str, None] = "case_version_revision_artifacts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "case_files",
        sa.Column(
            "latest_used_in_case_version_id",
            sa.String(),
            sa.ForeignKey("case_versions.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_case_files_latest_used_in_case_version_id",
        "case_files",
        ["latest_used_in_case_version_id"],
    )
    op.add_column(
        "case_versions",
        sa.Column(
            "version_processing_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.add_column("clinical_extractions", sa.Column("version_delta_context", sa.JSON(), nullable=True))
    op.add_column("clinical_extractions", sa.Column("merged_clinical_state", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("clinical_extractions", "merged_clinical_state")
    op.drop_column("clinical_extractions", "version_delta_context")
    op.drop_column("case_versions", "version_processing_metadata")
    op.drop_index("ix_case_files_latest_used_in_case_version_id", table_name="case_files")
    op.drop_column("case_files", "latest_used_in_case_version_id")
