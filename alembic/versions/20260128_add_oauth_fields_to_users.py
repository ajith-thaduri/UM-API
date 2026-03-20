"""add oauth fields to users

Revision ID: add_oauth_fields
Revises: 20260127_1230
Create Date: 2026-01-28 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = 'add_oauth_fields'
down_revision = '20260127_1230'
branch_labels = None
depends_on = None


def upgrade():
    # Add OAuth fields
    op.add_column('users', sa.Column('auth_provider', sa.String(length=50), nullable=True))
    op.add_column('users', sa.Column('provider_user_id', sa.String(length=255), nullable=True))
    op.add_column('users', sa.Column('provider_email', sa.String(length=255), nullable=True))
    op.add_column('users', sa.Column('avatar_url', sa.String(length=500), nullable=True))
    op.add_column('users', sa.Column('email_verified', sa.Boolean(), default=False, nullable=True))
    op.add_column('users', sa.Column('oauth_access_token', sa.Text(), nullable=True))  # Encrypted
    op.add_column('users', sa.Column('oauth_refresh_token', sa.Text(), nullable=True))  # Encrypted
    op.add_column('users', sa.Column('provider_data', sa.JSON(), nullable=True))
    
    # Create indexes for OAuth lookups
    op.create_index('idx_users_provider_user_id', 'users', ['auth_provider', 'provider_user_id'], unique=False)
    op.create_index('idx_users_provider_email', 'users', ['provider_email'], unique=False)
    
    # Set default auth_provider for existing users
    op.execute("UPDATE users SET auth_provider = 'password' WHERE hashed_password IS NOT NULL")
    op.execute("UPDATE users SET auth_provider = 'password' WHERE auth_provider IS NULL")


def downgrade():
    op.drop_index('idx_users_provider_email', table_name='users')
    op.drop_index('idx_users_provider_user_id', table_name='users')
    op.drop_column('users', 'provider_data')
    op.drop_column('users', 'oauth_refresh_token')
    op.drop_column('users', 'oauth_access_token')
    op.drop_column('users', 'email_verified')
    op.drop_column('users', 'avatar_url')
    op.drop_column('users', 'provider_email')
    op.drop_column('users', 'provider_user_id')
    op.drop_column('users', 'auth_provider')
