"""add_fk_to_entity_sources

Revision ID: 312592ba6920
Revises: page_rag_entities
Create Date: 2026-02-11 06:55:51.240509+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '312592ba6920'
down_revision: Union[str, None] = 'page_rag_entities'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add foreign key constraint to link entity_sources to entities
    op.create_foreign_key(
        'fk_entity_sources_entity_id',
        'entity_sources',
        'entities',
        ['entity_id'],
        ['entity_id'],
        ondelete='CASCADE'
    )


def downgrade() -> None:
    # Drop foreign key constraint
    op.drop_constraint('fk_entity_sources_entity_id', 'entity_sources', type_='foreignkey')
