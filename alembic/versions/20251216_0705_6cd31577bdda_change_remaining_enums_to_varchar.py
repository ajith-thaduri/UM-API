"""change_remaining_enums_to_varchar

Revision ID: 6cd31577bdda
Revises: 78e3506cde0f
Create Date: 2025-12-16 07:05:15.671628+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6cd31577bdda'
down_revision: Union[str, None] = '78e3506cde0f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Change decision_type from enum to VARCHAR
    op.execute("""
        ALTER TABLE decisions 
        ALTER COLUMN decision_type TYPE VARCHAR(50) 
        USING decision_type::text
    """)
    
    # Change status and priority in cases table
    op.execute("""
        ALTER TABLE cases 
        ALTER COLUMN status TYPE VARCHAR(50) 
        USING status::text
    """)
    op.execute("""
        ALTER TABLE cases 
        ALTER COLUMN priority TYPE VARCHAR(20) 
        USING priority::text
    """)
    
    # Change role in users table
    op.execute("""
        ALTER TABLE users 
        ALTER COLUMN role TYPE VARCHAR(30) 
        USING role::text
    """)
    
    # Drop the enum types (optional, but cleans up)
    op.execute('DROP TYPE IF EXISTS decisiontype')
    op.execute('DROP TYPE IF EXISTS casestatus')
    op.execute('DROP TYPE IF EXISTS priority')
    op.execute('DROP TYPE IF EXISTS userrole')


def downgrade() -> None:
    # Recreate enum types
    op.execute("""
        CREATE TYPE decisiontype AS ENUM (
            'APPROVED', 'DENIED', 'PENDING', 'NEEDS_CLARIFICATION'
        )
    """)
    op.execute("""
        CREATE TYPE casestatus AS ENUM (
            'UPLOADED', 'PROCESSING', 'EXTRACTING', 'TIMELINE_BUILDING', 
            'READY', 'REVIEWED', 'FAILED'
        )
    """)
    op.execute("""
        CREATE TYPE priority AS ENUM (
            'URGENT', 'HIGH', 'NORMAL', 'LOW'
        )
    """)
    op.execute("""
        CREATE TYPE userrole AS ENUM (
            'UM_NURSE', 'MEDICAL_DIRECTOR', 'ADMIN', 'AUDITOR'
        )
    """)
    
    # Change columns back to enums
    op.execute("""
        ALTER TABLE decisions 
        ALTER COLUMN decision_type TYPE decisiontype 
        USING decision_type::decisiontype
    """)
    op.execute("""
        ALTER TABLE cases 
        ALTER COLUMN status TYPE casestatus 
        USING status::casestatus
    """)
    op.execute("""
        ALTER TABLE cases 
        ALTER COLUMN priority TYPE priority 
        USING priority::priority
    """)
    op.execute("""
        ALTER TABLE users 
        ALTER COLUMN role TYPE userrole 
        USING role::userrole
    """)
