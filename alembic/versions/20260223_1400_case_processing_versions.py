"""Case processing versions: CaseVersion, version-scoped artifacts, backfill v1.

Revision ID: case_versioning_v1
Revises: 20260305_1200
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "case_versioning_v1"
down_revision: Union[str, None] = "20260305_1200"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "case_versions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("case_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("is_live", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("base_version_id", sa.String(), nullable=True),
        sa.Column("change_summary", sa.Text(), nullable=True),
        sa.Column("change_reasoning", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("processing_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("record_count", sa.Integer(), server_default="0"),
        sa.Column("page_count", sa.Integer(), server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["base_version_id"], ["case_versions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("case_id", "version_number", name="uq_case_versions_case_version_number"),
    )
    op.create_index("ix_case_versions_case_id", "case_versions", ["case_id"])
    op.create_index("ix_case_versions_base_version_id", "case_versions", ["base_version_id"])
    op.create_index("idx_case_versions_case_live", "case_versions", ["case_id", "is_live"])

    op.create_table(
        "case_version_files",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("case_version_id", sa.String(), nullable=False),
        sa.Column("case_file_id", sa.String(), nullable=False),
        sa.Column("file_role", sa.String(length=20), nullable=False),
        sa.Column("inherited_from_version_id", sa.String(), nullable=True),
        sa.Column("file_order_within_version", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["case_version_id"], ["case_versions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["case_file_id"], ["case_files.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["inherited_from_version_id"], ["case_versions.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("case_version_id", "case_file_id", name="uq_case_version_file_member"),
    )
    op.create_index("ix_case_version_files_case_version_id", "case_version_files", ["case_version_id"])
    op.create_index("ix_case_version_files_case_file_id", "case_version_files", ["case_file_id"])
    op.create_index(
        "idx_case_version_files_version_order",
        "case_version_files",
        ["case_version_id", "file_order_within_version"],
    )

    op.add_column("cases", sa.Column("live_version_id", sa.String(), nullable=True))
    op.add_column(
        "cases",
        sa.Column("latest_version_number", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column("cases", sa.Column("processing_version_id", sa.String(), nullable=True))
    op.create_foreign_key(
        "fk_cases_live_version_id", "cases", "case_versions", ["live_version_id"], ["id"]
    )
    op.create_foreign_key(
        "fk_cases_processing_version_id", "cases", "case_versions", ["processing_version_id"], ["id"]
    )
    op.create_index("idx_case_live_version", "cases", ["live_version_id"])

    op.add_column(
        "case_files",
        sa.Column("introduced_in_case_version_id", sa.String(), nullable=True),
    )
    op.create_foreign_key(
        "fk_case_files_introduced_version",
        "case_files",
        "case_versions",
        ["introduced_in_case_version_id"],
        ["id"],
    )
    op.create_index(
        "ix_case_files_introduced_in_case_version_id",
        "case_files",
        ["introduced_in_case_version_id"],
    )

    op.add_column("clinical_extractions", sa.Column("case_version_id", sa.String(), nullable=True))
    op.add_column("document_chunks", sa.Column("case_version_id", sa.String(), nullable=True))
    op.add_column("entity_sources", sa.Column("case_version_id", sa.String(), nullable=True))
    op.add_column("dashboard_snapshots", sa.Column("case_version_id", sa.String(), nullable=True))
    op.add_column("facet_results", sa.Column("case_version_id", sa.String(), nullable=True))
    op.add_column("source_links", sa.Column("case_version_id", sa.String(), nullable=True))
    op.add_column("privacy_vault", sa.Column("case_version_id", sa.String(), nullable=True))

    # Backfill: one version per case (v1)
    op.execute(
        """
        INSERT INTO case_versions (
            id, case_id, user_id, version_number, status, is_live,
            base_version_id, change_summary, change_reasoning,
            processing_started_at, processed_at, record_count, page_count, created_at
        )
        SELECT
            gen_random_uuid()::text,
            c.id,
            c.user_id,
            1,
            CASE
                WHEN c.status::text IN ('ready', 'reviewed') THEN 'ready'
                WHEN c.status::text = 'failed' THEN 'failed'
                ELSE 'processing'
            END,
            TRUE,
            NULL,
            NULL,
            NULL,
            NULL,
            NULL,
            COALESCE(c.record_count, 0),
            COALESCE(c.page_count, 0),
            NOW()
        FROM cases c;
        """
    )
    op.execute(
        """
        UPDATE cases c
        SET live_version_id = v.id,
            latest_version_number = 1
        FROM case_versions v
        WHERE v.case_id = c.id AND v.version_number = 1;
        """
    )
    op.execute(
        """
        UPDATE clinical_extractions e
        SET case_version_id = c.live_version_id
        FROM cases c
        WHERE e.case_id = c.id AND c.live_version_id IS NOT NULL;
        """
    )
    op.execute(
        """
        UPDATE document_chunks ch
        SET case_version_id = c.live_version_id
        FROM cases c
        WHERE ch.case_id = c.id AND c.live_version_id IS NOT NULL;
        """
    )
    op.execute(
        """
        UPDATE entity_sources es
        SET case_version_id = c.live_version_id
        FROM cases c
        WHERE es.case_id = c.id AND c.live_version_id IS NOT NULL;
        """
    )
    op.execute(
        """
        UPDATE dashboard_snapshots ds
        SET case_version_id = c.live_version_id
        FROM cases c
        WHERE ds.case_id = c.id AND c.live_version_id IS NOT NULL;
        """
    )
    op.execute(
        """
        UPDATE facet_results fr
        SET case_version_id = ds.case_version_id
        FROM dashboard_snapshots ds
        WHERE fr.snapshot_id = ds.id AND ds.case_version_id IS NOT NULL;
        """
    )
    op.execute(
        """
        UPDATE source_links sl
        SET case_version_id = fr.case_version_id
        FROM facet_results fr
        WHERE sl.facet_id = fr.id AND fr.case_version_id IS NOT NULL;
        """
    )
    op.execute(
        """
        UPDATE privacy_vault pv
        SET case_version_id = c.live_version_id
        FROM cases c
        WHERE pv.case_id = c.id AND c.live_version_id IS NOT NULL;
        """
    )
    op.execute(
        """
        INSERT INTO case_version_files (
            id, case_version_id, case_file_id, file_role, inherited_from_version_id, file_order_within_version
        )
        SELECT
            gen_random_uuid()::text,
            c.live_version_id,
            cf.id,
            'new',
            NULL,
            cf.file_order
        FROM case_files cf
        JOIN cases c ON cf.case_id = c.id
        WHERE c.live_version_id IS NOT NULL;
        """
    )
    op.execute(
        """
        UPDATE case_files cf
        SET introduced_in_case_version_id = c.live_version_id
        FROM cases c
        WHERE cf.case_id = c.id AND c.live_version_id IS NOT NULL;
        """
    )

    # Synthetic extraction row for cases that have chunks but no extraction (edge case)
    op.execute(
        """
        INSERT INTO clinical_extractions (
            id, case_id, case_version_id, user_id, extracted_data, created_at, updated_at
        )
        SELECT
            gen_random_uuid()::text,
            c.id,
            c.live_version_id,
            c.user_id,
            NULL,
            NOW(),
            NOW()
        FROM cases c
        WHERE c.live_version_id IS NOT NULL
          AND NOT EXISTS (
            SELECT 1 FROM clinical_extractions e WHERE e.case_version_id = c.live_version_id
          )
          AND EXISTS (
            SELECT 1 FROM document_chunks ch WHERE ch.case_id = c.id
          );
        """
    )

    # Enforce NOT NULL and FKs
    op.execute(
        """
        DO $d$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'clinical_extractions_case_id_key'
              AND conrelid = 'clinical_extractions'::regclass
          ) THEN
            ALTER TABLE clinical_extractions DROP CONSTRAINT clinical_extractions_case_id_key;
          END IF;
        END $d$;
        """
    )
    op.alter_column("clinical_extractions", "case_version_id", nullable=False)
    op.create_foreign_key(
        "fk_clinical_extractions_case_version",
        "clinical_extractions",
        "case_versions",
        ["case_version_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_clinical_extractions_case_version_id", "clinical_extractions", ["case_version_id"])
    op.create_unique_constraint(
        "uq_clinical_extractions_case_version_id", "clinical_extractions", ["case_version_id"]
    )

    op.alter_column("document_chunks", "case_version_id", nullable=False)
    op.create_foreign_key(
        "fk_document_chunks_case_version",
        "document_chunks",
        "case_versions",
        ["case_version_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_document_chunks_case_version_id", "document_chunks", ["case_version_id"])
    op.create_index(
        "idx_chunk_version_section", "document_chunks", ["case_version_id", "section_type"]
    )

    op.alter_column("entity_sources", "case_version_id", nullable=False)
    op.create_foreign_key(
        "fk_entity_sources_case_version",
        "entity_sources",
        "case_versions",
        ["case_version_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_entity_sources_case_version_id", "entity_sources", ["case_version_id"])

    op.alter_column("dashboard_snapshots", "case_version_id", nullable=False)
    op.create_foreign_key(
        "fk_dashboard_snapshots_case_version",
        "dashboard_snapshots",
        "case_versions",
        ["case_version_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_dashboard_snapshots_case_version_id", "dashboard_snapshots", ["case_version_id"])
    op.create_index(
        "idx_snapshot_version_user", "dashboard_snapshots", ["case_version_id", "user_id"]
    )

    op.alter_column("facet_results", "case_version_id", nullable=False)
    op.create_foreign_key(
        "fk_facet_results_case_version",
        "facet_results",
        "case_versions",
        ["case_version_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_facet_results_case_version_id", "facet_results", ["case_version_id"])

    op.alter_column("source_links", "case_version_id", nullable=False)
    op.create_foreign_key(
        "fk_source_links_case_version",
        "source_links",
        "case_versions",
        ["case_version_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_source_links_case_version_id", "source_links", ["case_version_id"])

    op.create_foreign_key(
        "fk_privacy_vault_case_version",
        "privacy_vault",
        "case_versions",
        ["case_version_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_privacy_vault_case_version_id", "privacy_vault", ["case_version_id"])


def downgrade() -> None:
    op.drop_index("ix_privacy_vault_case_version_id", table_name="privacy_vault")
    op.drop_constraint("fk_privacy_vault_case_version", "privacy_vault", type_="foreignkey")
    op.drop_column("privacy_vault", "case_version_id")

    op.drop_index("ix_source_links_case_version_id", table_name="source_links")
    op.drop_constraint("fk_source_links_case_version", "source_links", type_="foreignkey")
    op.drop_column("source_links", "case_version_id")

    op.drop_index("ix_facet_results_case_version_id", table_name="facet_results")
    op.drop_constraint("fk_facet_results_case_version", "facet_results", type_="foreignkey")
    op.drop_column("facet_results", "case_version_id")

    op.drop_index("idx_snapshot_version_user", table_name="dashboard_snapshots")
    op.drop_index("ix_dashboard_snapshots_case_version_id", table_name="dashboard_snapshots")
    op.drop_constraint("fk_dashboard_snapshots_case_version", "dashboard_snapshots", type_="foreignkey")
    op.drop_column("dashboard_snapshots", "case_version_id")

    op.drop_index("ix_entity_sources_case_version_id", table_name="entity_sources")
    op.drop_constraint("fk_entity_sources_case_version", "entity_sources", type_="foreignkey")
    op.drop_column("entity_sources", "case_version_id")

    op.drop_index("idx_chunk_version_section", table_name="document_chunks")
    op.drop_index("ix_document_chunks_case_version_id", table_name="document_chunks")
    op.drop_constraint("fk_document_chunks_case_version", "document_chunks", type_="foreignkey")
    op.drop_column("document_chunks", "case_version_id")

    op.drop_constraint("uq_clinical_extractions_case_version_id", "clinical_extractions", type_="unique")
    op.drop_index("ix_clinical_extractions_case_version_id", table_name="clinical_extractions")
    op.drop_constraint("fk_clinical_extractions_case_version", "clinical_extractions", type_="foreignkey")
    op.drop_column("clinical_extractions", "case_version_id")
    op.create_unique_constraint("clinical_extractions_case_id_key", "clinical_extractions", ["case_id"])

    op.drop_index("ix_case_files_introduced_in_case_version_id", table_name="case_files")
    op.drop_constraint("fk_case_files_introduced_version", "case_files", type_="foreignkey")
    op.drop_column("case_files", "introduced_in_case_version_id")

    op.drop_index("idx_case_live_version", table_name="cases")
    op.drop_constraint("fk_cases_processing_version_id", "cases", type_="foreignkey")
    op.drop_constraint("fk_cases_live_version_id", "cases", type_="foreignkey")
    op.drop_column("cases", "processing_version_id")
    op.drop_column("cases", "latest_version_number")
    op.drop_column("cases", "live_version_id")

    op.drop_table("case_version_files")
    op.drop_table("case_versions")
