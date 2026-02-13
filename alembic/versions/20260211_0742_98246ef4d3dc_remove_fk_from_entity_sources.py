"""remove_fk_from_entity_sources

Revision ID: 98246ef4d3dc
Revises: 312592ba6920
Create Date: 2026-02-11 07:42:47.645880+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '98246ef4d3dc'
down_revision: Union[str, None] = '312592ba6920'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop the foreign key constraint that requires entity_id to exist in entities table
    # This allows entity_sources to be used for things like timeline events that are not in the entities table
    op.drop_constraint("fk_entity_sources_entity_id", "entity_sources", type_="foreignkey")


def downgrade() -> None:
    # Re-add the foreign key constraint
    op.create_foreign_key(
        "fk_entity_sources_entity_id",
        "entity_sources", "entities",
        ["entity_id"], ["entity_id"],
        ondelete="CASCADE"
    )
