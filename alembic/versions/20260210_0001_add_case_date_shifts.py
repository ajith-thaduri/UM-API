"""Add case_date_shifts table for HIPAA Tier 2 date shifting

Revision ID: b1c2d3e4f5a6
Revises: a030f3bad946
Create Date: 2026-02-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, None] = "a030f3bad946"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "case_date_shifts",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("case_id", sa.String(), nullable=False),
        sa.Column("shift_days", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("case_id", name="uq_case_date_shift_case_id"),
    )
    op.create_index(op.f("ix_case_date_shifts_id"), "case_date_shifts", ["id"], unique=False)
    op.create_index(op.f("ix_case_date_shifts_case_id"), "case_date_shifts", ["case_id"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_case_date_shifts_case_id"), table_name="case_date_shifts")
    op.drop_index(op.f("ix_case_date_shifts_id"), table_name="case_date_shifts")
    op.drop_table("case_date_shifts")
