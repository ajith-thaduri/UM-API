"""Merge heads

Revision ID: 321a24ee1023
Revises: 053f02f6f2b9, cf9a1b2c3d4e
Create Date: 2026-02-13 07:03:31.421067+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '321a24ee1023'
down_revision: Union[str, None] = ('053f02f6f2b9', 'cf9a1b2c3d4e')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
