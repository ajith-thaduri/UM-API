"""change_facet_status_to_varchar

Revision ID: 9fe96edf8950
Revises: 3b91d254b128
Create Date: 2025-12-16 06:59:06.083316+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9fe96edf8950'
down_revision: Union[str, None] = '3b91d254b128'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Convert dashboard_snapshots.status and facet_results.status from enum to VARCHAR
    op.execute(
        """
        ALTER TABLE dashboard_snapshots
        ALTER COLUMN status TYPE VARCHAR(20)
        USING status::text
        """
    )

    op.execute(
        """
        ALTER TABLE facet_results
        ALTER COLUMN status TYPE VARCHAR(20)
        USING status::text
        """
    )

    # Drop the old enum type to avoid future conflicts
    op.execute("DROP TYPE IF EXISTS facetstatus")


def downgrade() -> None:
    # Recreate enum type
    op.execute(
        """
        CREATE TYPE facetstatus AS ENUM ('pending', 'ready', 'failed')
        """
    )

    # Convert columns back to enum
    op.execute(
        """
        ALTER TABLE dashboard_snapshots
        ALTER COLUMN status TYPE facetstatus
        USING status::facetstatus
        """
    )

    op.execute(
        """
        ALTER TABLE facet_results
        ALTER COLUMN status TYPE facetstatus
        USING status::facetstatus
        """
    )
