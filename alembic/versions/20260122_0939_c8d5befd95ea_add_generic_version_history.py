"""add_generic_version_history

Revision ID: c8d5befd95ea
Revises: ff1cd9c5b54f
Create Date: 2026-01-22 09:39:20.698385+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c8d5befd95ea'
down_revision: Union[str, None] = 'ff1cd9c5b54f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create version_history table
    op.create_table('version_history',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('referenceable_id', sa.String(), nullable=False),
    sa.Column('referenceable_table_name', sa.String(), nullable=False),
    sa.Column('version_number', sa.Integer(), nullable=False),
    sa.Column('event_type', sa.Enum('CREATE', 'UPDATE', 'ROLLBACK', 'DELETE', 'MIGRATED', name='versioneventtype', native_enum=False, length=20), nullable=False),
    sa.Column('object_changes', sa.JSON(), nullable=True),
    sa.Column('object_snapshot', sa.JSON(), nullable=True),
    sa.Column('changed_by_user_id', sa.String(), nullable=True),
    sa.Column('request_id', sa.String(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['changed_by_user_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('referenceable_table_name', 'referenceable_id', 'version_number', name='uq_version_history_ref_version')
    )
    op.create_index('ix_version_history_created_at_desc', 'version_history', [sa.text('created_at DESC')], unique=False)
    op.create_index('ix_version_history_ref', 'version_history', ['referenceable_table_name', 'referenceable_id'], unique=False)
    op.create_index('ix_version_history_ref_version_desc', 'version_history', ['referenceable_table_name', 'referenceable_id', sa.text('version_number DESC')], unique=False)
    
    # Update prompts table - SAFELY check if column exists first
    conn = op.get_bind()
    result = conn.execute(sa.text("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name='prompts' AND column_name='updated_by'
    """))
    if result.fetchone() is None:
        op.add_column('prompts', sa.Column('updated_by', sa.String(), nullable=True))
    
    # Check if FK exists before creating
    result = conn.execute(sa.text("""
        SELECT constraint_name 
        FROM information_schema.table_constraints 
        WHERE table_name='prompts' AND constraint_name='fk_prompts_updated_by_users'
    """))
    if result.fetchone() is None:
        op.create_foreign_key('fk_prompts_updated_by_users', 'prompts', 'users', ['updated_by'], ['id'], ondelete='SET NULL')


def downgrade() -> None:
    op.drop_constraint('fk_prompts_updated_by_users', 'prompts', type_='foreignkey')
    op.drop_column('prompts', 'updated_by')
    op.drop_index('ix_version_history_ref_version_desc', table_name='version_history')
    op.drop_index('ix_version_history_ref', table_name='version_history')
    op.drop_index('ix_version_history_created_at_desc', table_name='version_history')
    op.drop_table('version_history')
