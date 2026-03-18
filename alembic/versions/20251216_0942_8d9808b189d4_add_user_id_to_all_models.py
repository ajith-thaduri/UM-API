"""add_user_id_to_all_models

Revision ID: 8d9808b189d4
Revises: 6cd31577bdda
Create Date: 2025-12-16 09:42:08.399704+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8d9808b189d4'
down_revision: Union[str, None] = '6cd31577bdda'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Step 1: Create a default user for backfilling existing data
    # We'll use a system user ID
    default_user_id = '00000000-0000-0000-0000-000000000000'
    
    # Check if default user exists, if not create it
    op.execute(f"""
        INSERT INTO users (id, email, name, hashed_password, role, is_active, created_at)
        VALUES ('{default_user_id}', 'system@default.local', 'System Default User', NULL, 'um_nurse', true, NOW())
        ON CONFLICT (id) DO NOTHING
    """)
    
    # Step 2: Add user_id columns (nullable first for backfilling)
    
    # Cases: Change assigned_to to user_id and make it NOT NULL after backfill
    op.execute("""
        ALTER TABLE cases 
        ADD COLUMN IF NOT EXISTS user_id VARCHAR REFERENCES users(id) ON DELETE CASCADE
    """)
    # Backfill existing cases
    op.execute(f"""
        UPDATE cases 
        SET user_id = '{default_user_id}' 
        WHERE user_id IS NULL
    """)
    # Make NOT NULL and add index
    op.execute("""
        ALTER TABLE cases 
        ALTER COLUMN user_id SET NOT NULL
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_cases_user_id ON cases(user_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_cases_user_case_number ON cases(user_id, case_number)
    """)
    # Drop old assigned_to column if it exists and is different
    op.execute("""
        ALTER TABLE cases 
        DROP COLUMN IF EXISTS assigned_to
    """)
    
    # Case Files
    op.execute("""
        ALTER TABLE case_files 
        ADD COLUMN IF NOT EXISTS user_id VARCHAR REFERENCES users(id) ON DELETE CASCADE
    """)
    op.execute(f"""
        UPDATE case_files 
        SET user_id = (
            SELECT user_id FROM cases WHERE cases.id = case_files.case_id
        )
        WHERE user_id IS NULL
    """)
    op.execute("""
        ALTER TABLE case_files 
        ALTER COLUMN user_id SET NOT NULL
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_case_files_user_id ON case_files(user_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_case_files_user_case ON case_files(user_id, case_id)
    """)
    
    # Clinical Extractions
    op.execute("""
        ALTER TABLE clinical_extractions 
        ADD COLUMN IF NOT EXISTS user_id VARCHAR REFERENCES users(id) ON DELETE CASCADE
    """)
    op.execute(f"""
        UPDATE clinical_extractions 
        SET user_id = (
            SELECT user_id FROM cases WHERE cases.id = clinical_extractions.case_id
        )
        WHERE user_id IS NULL
    """)
    op.execute("""
        ALTER TABLE clinical_extractions 
        ALTER COLUMN user_id SET NOT NULL
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_clinical_extractions_user_id ON clinical_extractions(user_id)
    """)
    
    # Dashboard Snapshots
    op.execute("""
        ALTER TABLE dashboard_snapshots 
        ADD COLUMN IF NOT EXISTS user_id VARCHAR REFERENCES users(id) ON DELETE CASCADE
    """)
    op.execute(f"""
        UPDATE dashboard_snapshots 
        SET user_id = (
            SELECT user_id FROM cases WHERE cases.id = dashboard_snapshots.case_id
        )
        WHERE user_id IS NULL
    """)
    op.execute("""
        ALTER TABLE dashboard_snapshots 
        ALTER COLUMN user_id SET NOT NULL
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_dashboard_snapshots_user_id ON dashboard_snapshots(user_id)
    """)
    
    # Facet Results
    op.execute("""
        ALTER TABLE facet_results 
        ADD COLUMN IF NOT EXISTS user_id VARCHAR REFERENCES users(id) ON DELETE CASCADE
    """)
    op.execute(f"""
        UPDATE facet_results 
        SET user_id = (
            SELECT user_id FROM cases WHERE cases.id = facet_results.case_id
        )
        WHERE user_id IS NULL
    """)
    op.execute("""
        ALTER TABLE facet_results 
        ALTER COLUMN user_id SET NOT NULL
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_facet_results_user_id ON facet_results(user_id)
    """)
    
    # Document Chunks
    op.execute("""
        ALTER TABLE document_chunks 
        ADD COLUMN IF NOT EXISTS user_id VARCHAR REFERENCES users(id) ON DELETE CASCADE
    """)
    op.execute(f"""
        UPDATE document_chunks 
        SET user_id = (
            SELECT user_id FROM cases WHERE cases.id = document_chunks.case_id
        )
        WHERE user_id IS NULL
    """)
    op.execute("""
        ALTER TABLE document_chunks 
        ALTER COLUMN user_id SET NOT NULL
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_document_chunks_user_id ON document_chunks(user_id)
    """)
    
    # Decisions
    op.execute("""
        ALTER TABLE decisions 
        ADD COLUMN IF NOT EXISTS user_id VARCHAR REFERENCES users(id) ON DELETE CASCADE
    """)
    op.execute(f"""
        UPDATE decisions 
        SET user_id = (
            SELECT user_id FROM cases WHERE cases.id = decisions.case_id
        )
        WHERE user_id IS NULL
    """)
    op.execute("""
        ALTER TABLE decisions 
        ALTER COLUMN user_id SET NOT NULL
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_decisions_user_id ON decisions(user_id)
    """)
    
    # Case Notes
    op.execute("""
        ALTER TABLE case_notes 
        ADD COLUMN IF NOT EXISTS user_id VARCHAR REFERENCES users(id) ON DELETE CASCADE
    """)
    op.execute(f"""
        UPDATE case_notes 
        SET user_id = (
            SELECT user_id FROM cases WHERE cases.id = case_notes.case_id
        )
        WHERE user_id IS NULL
    """)
    op.execute("""
        ALTER TABLE case_notes 
        ALTER COLUMN user_id SET NOT NULL
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_case_notes_user_id ON case_notes(user_id)
    """)


def downgrade() -> None:
    # Drop indexes
    op.execute("DROP INDEX IF EXISTS idx_case_notes_user_id")
    op.execute("DROP INDEX IF EXISTS idx_decisions_user_id")
    op.execute("DROP INDEX IF EXISTS idx_document_chunks_user_id")
    op.execute("DROP INDEX IF EXISTS idx_facet_results_user_id")
    op.execute("DROP INDEX IF EXISTS idx_dashboard_snapshots_user_id")
    op.execute("DROP INDEX IF EXISTS idx_clinical_extractions_user_id")
    op.execute("DROP INDEX IF EXISTS idx_case_files_user_case")
    op.execute("DROP INDEX IF EXISTS idx_case_files_user_id")
    op.execute("DROP INDEX IF EXISTS idx_cases_user_case_number")
    op.execute("DROP INDEX IF EXISTS idx_cases_user_id")
    
    # Drop user_id columns
    op.execute("ALTER TABLE case_notes DROP COLUMN IF EXISTS user_id")
    op.execute("ALTER TABLE decisions DROP COLUMN IF EXISTS user_id")
    op.execute("ALTER TABLE document_chunks DROP COLUMN IF EXISTS user_id")
    op.execute("ALTER TABLE facet_results DROP COLUMN IF EXISTS user_id")
    op.execute("ALTER TABLE dashboard_snapshots DROP COLUMN IF EXISTS user_id")
    op.execute("ALTER TABLE clinical_extractions DROP COLUMN IF EXISTS user_id")
    op.execute("ALTER TABLE case_files DROP COLUMN IF EXISTS user_id")
    op.execute("ALTER TABLE cases DROP COLUMN IF EXISTS user_id")
    
    # Recreate assigned_to if needed (optional)
    op.execute("""
        ALTER TABLE cases 
        ADD COLUMN IF NOT EXISTS assigned_to VARCHAR REFERENCES users(id)
    """)
