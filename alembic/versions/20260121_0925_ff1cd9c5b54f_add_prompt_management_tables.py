"""add_prompt_management_tables

Revision ID: ff1cd9c5b54f
Revises: 1c24b179236c
Create Date: 2026-01-21 09:25:18.588773+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ff1cd9c5b54f'
down_revision: Union[str, None] = '1c24b179236c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create prompts table
    op.create_table(
        'prompts',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('category', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('template', sa.Text(), nullable=False),
        sa.Column('system_message', sa.Text(), nullable=True),
        sa.Column('variables', sa.JSON(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_prompts_id'), 'prompts', ['id'], unique=False)
    op.create_index(op.f('ix_prompts_category'), 'prompts', ['category'], unique=False)

    # Create prompt_versions table
    op.create_table(
        'prompt_versions',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('prompt_id', sa.String(), nullable=False),
        sa.Column('version_number', sa.Integer(), nullable=False),
        sa.Column('template', sa.Text(), nullable=False),
        sa.Column('system_message', sa.Text(), nullable=True),
        sa.Column('changed_by', sa.String(), nullable=True),
        sa.Column('change_notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['prompt_id'], ['prompts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['changed_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_prompt_versions_prompt_id'), 'prompt_versions', ['prompt_id'], unique=False)
    op.create_index(op.f('ix_prompt_versions_version_number'), 'prompt_versions', ['version_number'], unique=False)

    # Create active_prompt_version table (singleton)
    op.create_table(
        'active_prompt_version',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('current_version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('active_prompt_version')
    op.drop_index(op.f('ix_prompt_versions_version_number'), table_name='prompt_versions')
    op.drop_index(op.f('ix_prompt_versions_prompt_id'), table_name='prompt_versions')
    op.drop_table('prompt_versions')
    op.drop_index(op.f('ix_prompts_category'), table_name='prompts')
    op.drop_index(op.f('ix_prompts_id'), table_name='prompts')
    op.drop_table('prompts')
