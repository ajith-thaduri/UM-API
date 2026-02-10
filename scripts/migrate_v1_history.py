"""Data migration script to backfill version_history from prompt_versions"""

import os
import sys
import uuid
from datetime import datetime, timezone
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Add the project root to sys.path to import app modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.core.config import settings
from app.models.version_history import VersionEventType

def migrate_history():
    print("Starting history migration...")
    
    # Create engine and session
    engine = create_engine(settings.DATABASE_URL)
    Session = sessionmaker(bind=engine)
    db = Session()
    
    try:
        # 1. Fetch all old prompt versions
        # We need to reconstruct snapshots. prompt_versions has template and system_message.
        # We also need name, category, and variables from the main prompts table.
        
        old_versions = db.execute(text("""
            SELECT DISTINCT ON (pv.prompt_id, pv.version_number)
                   pv.prompt_id, pv.version_number, pv.template, pv.system_message, 
                   pv.changed_by, pv.change_notes, pv.created_at,
                   p.name, p.category, p.variables
            FROM prompt_versions pv
            JOIN prompts p ON pv.prompt_id = p.id
            ORDER BY pv.prompt_id, pv.version_number ASC, pv.created_at DESC
        """)).fetchall()
        
        print(f"Found {len(old_versions)} old versions to migrate.")
        
        count = 0
        for row in old_versions:
            # Prepare snapshot
            snapshot = {
                "template": row.template,
                "system_message": row.system_message,
                "name": row.name,
                "category": row.category,
                "variables": row.variables
            }
            
            # Prepare changes (for migrated data, we might not have the full diff, 
            # but we can store the change notes)
            changes = {"change_notes": row.change_notes} if row.change_notes else None
            
            # Insert into version_history
            db.execute(text("""
                INSERT INTO version_history (
                    id, referenceable_id, referenceable_table_name, version_number,
                    event_type, object_changes, object_snapshot, 
                    changed_by_user_id, created_at
                ) VALUES (
                    :id, :ref_id, :table_name, :version,
                    :event_type, :changes, :snapshot,
                    :user_id, :created_at
                )
            """), {
                "id": str(uuid.uuid4()),
                "ref_id": row.prompt_id,
                "table_name": "prompts",
                "version": row.version_number,
                "event_type": VersionEventType.MIGRATED.value,
                "changes": sa_json_dump(changes),
                "snapshot": sa_json_dump(snapshot),
                "user_id": row.changed_by,
                "created_at": row.created_at
            })
            count += 1
            
        db.commit()
        print(f"Successfully migrated {count} history records.")
        
    except Exception as e:
        db.rollback()
        print(f"Error during migration: {e}")
        raise e
    finally:
        db.close()

def sa_json_dump(data):
    import json
    return json.dumps(data) if data is not None else None

if __name__ == "__main__":
    migrate_history()
