#!/usr/bin/env python3
"""
Script to reseed all prompts from the backup JSON file.
This ensures all required prompts (including patient_info_extraction) are present in the database.
"""

import sys
import os
import json
from datetime import datetime, timezone

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import SessionLocal
from app.models.prompt import Prompt

BACKUP_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".prompt_backup.json")

def reseed_prompts():
    """Reseed prompts from backup JSON"""
    if not os.path.exists(BACKUP_FILE):
        print(f"Error: Backup file {BACKUP_FILE} not found.")
        return

    with open(BACKUP_FILE, 'r') as f:
        prompts_dict = json.load(f)

    db = SessionLocal()
    try:
        updated_count = 0
        created_count = 0
        
        for prompt_id, data in prompts_dict.items():
            template = data.get("template")
            system_message = data.get("system_message")
            
            # Extract variables from template using regex
            import re
            variables = list(set(re.findall(r'\{([a-zA-Z0-9_]+)\}', template)))
            
            prompt = db.query(Prompt).filter(Prompt.id == prompt_id).first()
            
            if prompt:
                # Update existing prompt
                prompt.template = template
                prompt.system_message = system_message
                prompt.variables = variables
                prompt.updated_at = datetime.now(timezone.utc)
                updated_count += 1
            else:
                # Create new prompt
                new_prompt = Prompt(
                    id=prompt_id,
                    name=prompt_id.replace("_", " ").title(),
                    category="clinical_extraction" if "extraction" in prompt_id else "general",
                    template=template,
                    system_message=system_message,
                    variables=variables,
                    is_active=True,
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc)
                )
                db.add(new_prompt)
                created_count += 1
                # print(f"  + Created: {prompt_id}")
        
        db.commit()
        print(f"\nSummary:")
        print(f"  Created: {created_count}")
        print(f"  Updated: {updated_count}")
        print(f"  Total:   {len(prompts_dict)}")
        
    except Exception as e:
        db.rollback()
        print(f"Error: {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    print("=== Reseeding Prompts from Backup ===\n")
    reseed_prompts()
    print("\nDone!")
