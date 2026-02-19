
import sys
import os
import json
from sqlalchemy import create_engine, text

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.core.config import settings
from app.db.session import SessionLocal
from app.models.prompt import Prompt

# Configuration
SOURCE_DB_URL = "postgresql://utility:ZDqEnVyZVxSfGWALtZwEhMAmSZSP3gkN@dpg-d50fabggjchc73cbbmc0-a.oregon-postgres.render.com/utlitymanagment"

def migrate_prompts():
    print(f"--- Prompt Migration Tool (ORM Mode) ---")
    print(f"Source: {SOURCE_DB_URL.split('@')[1]}")  # Hide credentials in logs
    
    target_url = str(settings.DATABASE_URL)
    print(f"Target: {target_url.split('@')[1] if '@' in target_url else 'Local'}")

    # 1. Connect to Source (READ ONLY)
    source_engine = create_engine(SOURCE_DB_URL)
    prompts_data = []
    
    try:
        with source_engine.connect() as source_conn:
            print("Fetching prompts from Source DB...")
            result = source_conn.execute(text("SELECT * FROM prompts"))
            prompts_data = [dict(row) for row in result.mappings()]
            print(f"Found {len(prompts_data)} prompts in Source.")
            
    except Exception as e:
        print(f"Failed to fetch from Source DB: {e}")
        return

    if not prompts_data:
        print("No prompts found to migrate.")
        return

    # 2. Connect to Target (using ORM Session)
    db = SessionLocal()
    
    try:
        print("Writing to Target DB...")
        
        # Get valid columns for Prompt model
        valid_cols = set(c.name for c in Prompt.__table__.columns)
        
        success_count = 0
        for row in prompts_data:
            # Filter data to valid columns
            clean_data = {k: v for k, v in row.items() if k in valid_cols}
            
            # Special handling for JSON fields if they come as strings
            if "variables" in clean_data:
                val = clean_data["variables"]
                if isinstance(val, str):
                    try:
                        clean_data["variables"] = json.loads(val)
                    except json.JSONDecodeError:
                         # Fallback or keep as is? Keep as empty list if fails
                         clean_data["variables"] = []
                elif val is None:
                    clean_data["variables"] = []
            
            # FK Violation Fix: Source updated_by user might not exist in target.
            # Set to None to be safe.
            if "updated_by" in clean_data:
                clean_data["updated_by"] = None
            
            # Create ORM object (detached)
            # We use merge to upsert based on Primary Key (id)
            prompt = Prompt(**clean_data)
            db.merge(prompt)
            success_count += 1
            
        db.commit()
        print(f"Successfully migrated {success_count} prompts!")
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        db.rollback()
        print(f"Error writing to Target DB: {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    migrate_prompts()
