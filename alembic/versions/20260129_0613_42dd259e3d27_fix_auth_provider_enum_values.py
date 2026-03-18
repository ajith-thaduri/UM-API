"""fix_auth_provider_enum_values

Revision ID: 42dd259e3d27
Revises: add_oauth_fields
Create Date: 2026-01-29 06:13:10.660779+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '42dd259e3d27'
down_revision: Union[str, None] = 'add_oauth_fields'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Check if enum type exists and drop it if it does
    # Then ensure column is VARCHAR (not enum) since we use native_enum=False
    
    # First, check if authprovider enum type exists
    conn = op.get_bind()
    result = conn.execute(sa.text("""
        SELECT EXISTS (
            SELECT 1 FROM pg_type WHERE typname = 'authprovider'
        )
    """))
    enum_exists = result.scalar()
    
    if enum_exists:
        # Drop the enum type (this will fail if column still uses it, so we need to convert column first)
        # Convert column to VARCHAR first
        op.execute("ALTER TABLE users ALTER COLUMN auth_provider TYPE VARCHAR(50) USING auth_provider::text")
        # Now drop the enum type
        op.execute("DROP TYPE IF EXISTS authprovider")
    else:
        # Just ensure it's VARCHAR
        op.execute("ALTER TABLE users ALTER COLUMN auth_provider TYPE VARCHAR(50) USING auth_provider::text")
    
    # Ensure all existing values are lowercase (matching enum values)
    # The enum values are: PASSWORD = "password", GOOGLE = "google"
    op.execute("UPDATE users SET auth_provider = LOWER(auth_provider) WHERE auth_provider IS NOT NULL")
    
    # Set default for NULL values
    op.execute("UPDATE users SET auth_provider = 'password' WHERE auth_provider IS NULL AND hashed_password IS NOT NULL")


def downgrade() -> None:
    # Revert to enum type if needed (but we'll keep it as VARCHAR for simplicity)
    pass
