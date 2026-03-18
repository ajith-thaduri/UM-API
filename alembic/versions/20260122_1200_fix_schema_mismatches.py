"""fix_schema_mismatches

Revision ID: 20260122_1200_fix_schema_mismatches
Revises: 86ea19bffcea
Create Date: 2026-01-22 12:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260122_1200'
down_revision: Union[str, None] = '86ea19bffcea'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add user_id to source_links table
    # Add nullable column first
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = [c['name'] for c in inspector.get_columns('source_links')]
    
    if 'user_id' not in columns:
        op.add_column('source_links', sa.Column('user_id', sa.String(), nullable=True))
    
    # Backfill user_id from related cases
    op.execute("""
        UPDATE source_links 
        SET user_id = (
            SELECT user_id FROM cases WHERE cases.id = source_links.case_id
        )
        WHERE user_id IS NULL
    """)
    
    # Also handle cases where user_id might still be null (orphaned links?) 
    # Use system default user if we can't find a case match, or just leave null if we can't enforce it yet
    # But the model says nullable=False.
    # Let's check if there's a default user we can use. 
    # In previous migrations we used '00000000-0000-0000-0000-000000000000'.
    op.execute("""
        UPDATE source_links
        SET user_id = '00000000-0000-0000-0000-000000000000'
        WHERE user_id IS NULL
    """)

    # Now make it NOT NULL
    op.alter_column('source_links', 'user_id', nullable=False)
    
    # Add foreign key and index
    fks = [fk['name'] for fk in inspector.get_foreign_keys('source_links')]
    if 'fk_source_links_user_id_users' not in fks:
        op.create_foreign_key(
            'fk_source_links_user_id_users',
            'source_links', 'users',
            ['user_id'], ['id'],
            ondelete='CASCADE'
        )
    
    indexes = [ix['name'] for ix in inspector.get_indexes('source_links')]
    if 'ix_source_links_user_id' not in indexes:
        op.create_index(op.f('ix_source_links_user_id'), 'source_links', ['user_id'], unique=False)


def downgrade() -> None:
    # Remove user_id from source_links
    op.drop_index(op.f('ix_source_links_user_id'), table_name='source_links')
    op.drop_constraint('fk_source_links_user_id_users', 'source_links', type_='foreignkey')
    op.drop_column('source_links', 'user_id')
