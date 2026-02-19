"""add_case_file_model_and_remove_file_path

Revision ID: 4cbb47fa5159
Revises: 671ec48a3da3
Create Date: 2025-12-05 15:20:19.657741+00:00

"""
from typing import Sequence, Union
import logging

from alembic import op
import sqlalchemy as sa

logger = logging.getLogger(__name__)


# revision identifiers, used by Alembic.
revision: str = '4cbb47fa5159'
down_revision: Union[str, None] = '671ec48a3da3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create case_files table
    op.create_table('case_files',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('case_id', sa.String(), nullable=False),
        sa.Column('file_name', sa.String(), nullable=False),
        sa.Column('file_path', sa.String(), nullable=False),
        sa.Column('file_size', sa.Integer(), nullable=False),
        sa.Column('page_count', sa.Integer(), nullable=True),
        sa.Column('file_order', sa.Integer(), nullable=True),
        sa.Column('uploaded_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['case_id'], ['cases.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_case_files_id'), 'case_files', ['id'], unique=False)
    op.create_index(op.f('ix_case_files_case_id'), 'case_files', ['case_id'], unique=False)
    
    # Migrate existing file_path data to case_files table
    try:
        connection = op.get_bind()
        # Check if file_path column exists before querying
        inspector = sa.inspect(connection)
        columns = [col['name'] for col in inspector.get_columns('cases')]
        
        if 'file_path' in columns:
            result = connection.execute(sa.text("SELECT id, file_path FROM cases WHERE file_path IS NOT NULL AND file_path != ''"))
            cases = result.fetchall()
            
            import uuid
            from datetime import datetime
            import os
            
            for case_id, file_path in cases:
                if file_path and os.path.exists(file_path):
                    try:
                        file_name = os.path.basename(file_path)
                        file_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0
                        file_id = str(uuid.uuid4())
                        
                        connection.execute(sa.text("""
                            INSERT INTO case_files (id, case_id, file_name, file_path, file_size, page_count, file_order, uploaded_at)
                            VALUES (:id, :case_id, :file_name, :file_path, :file_size, 0, 0, :uploaded_at)
                        """), {
                            'id': file_id,
                            'case_id': case_id,
                            'file_name': file_name,
                            'file_path': file_path,
                            'file_size': file_size,
                            'uploaded_at': datetime.utcnow()
                        })
                    except Exception as e:
                        # Log error but continue with other cases
                        logger.warning(f"Failed to migrate file for case {case_id}: {e}")
                        continue
            
            # Remove file_path column from cases table
            if 'file_path' in columns:
                op.drop_column('cases', 'file_path')
    except Exception as e:
        # If migration fails, log but don't stop - column might not exist
        logger.warning(f"File migration step encountered an issue: {e}")
        # Still try to drop column if it exists
        try:
            inspector = sa.inspect(op.get_bind())
            columns = [col['name'] for col in inspector.get_columns('cases')]
            if 'file_path' in columns:
                op.drop_column('cases', 'file_path')
        except:
            pass


def downgrade() -> None:
    # Add file_path column back to cases table
    op.add_column('cases', sa.Column('file_path', sa.String(), nullable=True))
    
    # Migrate data back (take first file from case_files)
    connection = op.get_bind()
    result = connection.execute(sa.text("""
        SELECT case_id, file_path 
        FROM case_files 
        WHERE file_order = 0 OR file_order = (SELECT MIN(file_order) FROM case_files cf2 WHERE cf2.case_id = case_files.case_id)
    """))
    files = result.fetchall()
    
    for case_id, file_path in files:
        connection.execute(sa.text("""
            UPDATE cases SET file_path = :file_path WHERE id = :case_id
        """), {
            'file_path': file_path,
            'case_id': case_id
        })
    
    # Drop case_files table
    op.drop_index(op.f('ix_case_files_case_id'), table_name='case_files')
    op.drop_index(op.f('ix_case_files_id'), table_name='case_files')
    op.drop_table('case_files')
