"""Script to resolve database inconsistencies like orphaned entity_sources"""

import sys
import os
from sqlalchemy.orm import Session
from sqlalchemy import text

# Add the parent directory to sys.path to import app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import SessionLocal, engine

def heal_database():
    print("🏥 Starting database healing process...")
    
    db = SessionLocal()
    try:
        # 1. Clean up orphaned entity_sources
        print("🔍 Checking for orphaned entity_sources (missing document_chunks)...")
        
        # Check if tables exist first
        tables_check = db.execute(text("SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname = 'public'")).fetchall()
        table_names = [t[0] for t in tables_check]
        
        if 'entity_sources' in table_names and 'document_chunks' in table_names:
            orphaned_count = db.execute(text("""
                DELETE FROM entity_sources 
                WHERE chunk_id IS NOT NULL 
                AND chunk_id NOT IN (SELECT id FROM document_chunks)
            """)).rowcount
            print(f"✅ Deleted {orphaned_count} orphaned entity_sources records.")
        else:
            print("ℹ️ Tables 'entity_sources' or 'document_chunks' not found yet. Skipping orphaned cleanup.")

        # 2. Add missing foreign key constraints if they are missing
        # This prevents the 'ForeignKeyViolation' during migration by doing it manually and safely
        # but we'll let Alembic handle the actual schema changes.
        # This script just prepares the DATA.
        
        db.commit()
        print("✨ Database healing complete!")
        
    except Exception as e:
        print(f"❌ Error during database healing: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    heal_database()
