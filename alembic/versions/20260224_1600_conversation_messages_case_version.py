"""Add case_version_id to conversation_messages for version-scoped chat.

Revision ID: conv_msg_case_version
Revises: case_versioning_v1
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "conv_msg_case_version"
down_revision: Union[str, None] = "case_versioning_v1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "conversation_messages",
        sa.Column("case_version_id", sa.String(), nullable=True),
    )
    op.create_foreign_key(
        "fk_conversation_messages_case_version_id",
        "conversation_messages",
        "case_versions",
        ["case_version_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_conversation_case_user_version",
        "conversation_messages",
        ["case_id", "user_id", "case_version_id"],
        unique=False,
    )
    op.execute(
        """
        UPDATE conversation_messages AS cm
        SET case_version_id = c.live_version_id
        FROM cases AS c
        WHERE cm.case_id = c.id
          AND cm.case_version_id IS NULL
          AND c.live_version_id IS NOT NULL
        """
    )


def downgrade() -> None:
    op.drop_index("ix_conversation_case_user_version", table_name="conversation_messages")
    op.drop_constraint(
        "fk_conversation_messages_case_version_id",
        "conversation_messages",
        type_="foreignkey",
    )
    op.drop_column("conversation_messages", "case_version_id")
