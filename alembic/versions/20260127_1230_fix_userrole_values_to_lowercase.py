"""fix_userrole_values_to_lowercase

Revision ID: 20260127_1230
Revises: 20260122_1200
Create Date: 2026-01-27 12:30:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260127_1230'
down_revision: Union[str, None] = '20260122_1200'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Update existing user role values from uppercase to lowercase
    # This is needed because the code now uses lowercase values
    op.execute("""
        UPDATE users 
        SET role = LOWER(role)
        WHERE role IN ('UM_NURSE', 'MEDICAL_DIRECTOR', 'ADMIN', 'AUDITOR')
    """)


def downgrade() -> None:
    # Revert to uppercase values if needed
    op.execute("""
        UPDATE users 
        SET role = UPPER(role)
        WHERE role IN ('um_nurse', 'medical_director', 'admin', 'auditor')
    """)
