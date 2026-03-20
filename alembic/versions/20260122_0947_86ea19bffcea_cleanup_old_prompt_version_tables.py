"""cleanup_old_prompt_version_tables

Revision ID: 86ea19bffcea
Revises: c8d5befd95ea
Create Date: 2026-01-22 09:47:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '86ea19bffcea'
down_revision: Union[str, None] = 'c8d5befd95ea'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop old prompt version tables
    op.drop_table('active_prompt_version')
    op.drop_table('prompt_versions')


def downgrade() -> None:
    # Re-create prompt_versions
    op.create_table('prompt_versions',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('prompt_id', sa.String(), nullable=False),
    sa.Column('version_number', sa.Integer(), nullable=False),
    sa.Column('template', sa.Text(), nullable=False),
    sa.Column('system_message', sa.Text(), nullable=True),
    sa.Column('changed_by', sa.String(), nullable=True),
    sa.Column('change_notes', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['changed_by'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['prompt_id'], ['prompts.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    
    # Re-create active_prompt_version
    op.create_table('active_prompt_version',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('current_version', sa.Integer(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
