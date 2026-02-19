"""add source_mapping to clinical_extractions

Revision ID: 20251208_0900_add_source_mapping
Revises: 4cbb47fa5159
Create Date: 2025-12-08 09:00:00.000000
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20251208_0900_add_source_mapping"
down_revision: Union[str, None] = "4cbb47fa5159"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "clinical_extractions",
        sa.Column("source_mapping", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("clinical_extractions", "source_mapping")






