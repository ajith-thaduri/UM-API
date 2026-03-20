"""add dashboard snapshot and facet tables

Revision ID: 20251211_0001
Revises: 20251208_0900_add_source_mapping_to_clinical_extractions
Create Date: 2025-12-11
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20251211_0001"
down_revision = "20251208_0900_add_source_mapping"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dashboard_snapshots",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("case_id", sa.String(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.Enum("pending", "ready", "failed", name="facetstatus"), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_dashboard_snapshots_case_id", "dashboard_snapshots", ["case_id"]
    )

    op.create_table(
        "facet_results",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("snapshot_id", sa.String(), nullable=False),
        sa.Column("case_id", sa.String(), nullable=False),
        sa.Column("facet_type", sa.Enum("summary", "clinical", "timeline", "red_flags", "contradictions", name="facettype"), nullable=False),
        sa.Column("status", sa.Enum("pending", "ready", "failed", name="facetstatus"), nullable=False),
        sa.Column("content", sa.JSON(), nullable=True),
        sa.Column("sources", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["snapshot_id"], ["dashboard_snapshots.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_facet_results_case_id", "facet_results", ["case_id"])

    op.create_table(
        "source_links",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("case_id", sa.String(), nullable=False),
        sa.Column("facet_id", sa.String(), nullable=False),
        sa.Column("item_id", sa.String(), nullable=False),
        sa.Column("file_id", sa.String(), nullable=True),
        sa.Column("file_name", sa.String(), nullable=True),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("snippet", sa.Text(), nullable=True),
        sa.Column("full_text", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["facet_id"], ["facet_results.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_source_links_case_id", "source_links", ["case_id"])
    op.create_index("ix_source_links_facet_id", "source_links", ["facet_id"])


def downgrade() -> None:
    op.drop_index("ix_source_links_facet_id", table_name="source_links")
    op.drop_index("ix_source_links_case_id", table_name="source_links")
    op.drop_table("source_links")
    op.drop_index("ix_facet_results_case_id", table_name="facet_results")
    op.drop_table("facet_results")
    op.drop_index("ix_dashboard_snapshots_case_id", table_name="dashboard_snapshots")
    op.drop_table("dashboard_snapshots")
    op.execute("DROP TYPE IF EXISTS facetstatus")
    op.execute("DROP TYPE IF EXISTS facettype")

