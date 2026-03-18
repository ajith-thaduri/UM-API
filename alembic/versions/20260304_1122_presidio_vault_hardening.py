"""Presidio vault hardening: is_active flag + partial unique index on privacy_vault.

This migration:
1. Adds `is_active` boolean column to `privacy_vault` (backfills to TRUE).
2. Deduplicates: for cases with multiple vaults, keeps only the most recently
   created vault as active (is_active=TRUE), older ones set to FALSE.
3. Creates a partial unique index `uq_privacy_vault_active_case` on (case_id)
   WHERE is_active = TRUE — enforces one active vault per case at the DB level.
4. Upgrades created_at / expires_at to timezone-aware DateTime.

NOTE: `case_date_shifts` is intentionally not dropped — preserved for historical
rows. No new code writes to it. Future cleanup migration can DROP safely.

Revision ID: presidio_vault_hardening_20260304
Revises: 20260213_1305
Create Date: 2026-03-04 11:52:00
"""

from alembic import op
import sqlalchemy as sa

revision = "vault_hardening_v1"
down_revision = "20260213_1305"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. Add is_active column ────────────────────────────────────────────────
    op.add_column(
        "privacy_vault",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )

    # ── 2. Set all rows to TRUE initially ─────────────────────────────────────
    op.execute("UPDATE privacy_vault SET is_active = TRUE")

    # ── 3. Deactivate older duplicates — keep only the latest per case_id ─────
    # Strategy: For each case_id that has more than one vault row, set is_active=FALSE
    # on all but the most recently created one (highest created_at).
    op.execute(
        """
        UPDATE privacy_vault pv
        SET is_active = FALSE
        WHERE pv.id NOT IN (
            SELECT DISTINCT ON (case_id) id
            FROM privacy_vault
            ORDER BY case_id, created_at DESC NULLS LAST, id DESC
        )
        """
    )

    # ── 4. Upgrade datetime columns to timezone-aware ─────────────────────────
    op.alter_column(
        "privacy_vault",
        "created_at",
        type_=sa.DateTime(timezone=True),
        existing_type=sa.DateTime(),
        existing_nullable=False,
    )
    op.alter_column(
        "privacy_vault",
        "expires_at",
        type_=sa.DateTime(timezone=True),
        existing_type=sa.DateTime(),
        existing_nullable=True,
    )

    # ── 5. Create partial unique index outside the current transaction ─────────
    # Alembic uses transactional DDL; we step out via raw COMMIT/BEGIN to allow
    # the index creation (normal CREATE INDEX, not CONCURRENTLY).
    bind = op.get_bind()
    bind.execute(sa.text("COMMIT"))
    bind.execute(
        sa.text(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_privacy_vault_active_case
            ON privacy_vault (case_id)
            WHERE (is_active = TRUE)
            """
        )
    )
    bind.execute(sa.text("BEGIN"))


def downgrade() -> None:
    # Revert datetime types
    op.alter_column(
        "privacy_vault",
        "created_at",
        type_=sa.DateTime(),
        existing_type=sa.DateTime(timezone=True),
        existing_nullable=False,
    )
    op.alter_column(
        "privacy_vault",
        "expires_at",
        type_=sa.DateTime(),
        existing_type=sa.DateTime(timezone=True),
        existing_nullable=True,
    )

    op.execute("DROP INDEX IF EXISTS uq_privacy_vault_active_case")
    op.drop_column("privacy_vault", "is_active")
