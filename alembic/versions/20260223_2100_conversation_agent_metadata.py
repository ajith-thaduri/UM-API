"""Add agent_metadata JSON to conversation_messages for case agent traces."""

from alembic import op
import sqlalchemy as sa


revision = "20260223_2100_agent_meta"
down_revision = "phase2_case_vault_merge"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "conversation_messages",
        sa.Column("agent_metadata", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("conversation_messages", "agent_metadata")
