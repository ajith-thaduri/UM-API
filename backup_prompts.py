import os
import sys
import json

# Add the app directory to sys.path
sys.path.append(os.getcwd())

from app.db.session import SessionLocal
from app.repositories.prompt_repository import prompt_repository

def backup_prompts():
    db = SessionLocal()
    
    try:
        p1 = prompt_repository.get_by_id(db, "summary_generation")
        p2 = prompt_repository.get_by_id(db, "executive_summary_generation")
        
        backup_data = {}
        
        if p1:
            backup_data["summary_generation"] = {
                "template": p1.template,
                "system_message": p1.system_message
            }
            
        if p2:
            backup_data["executive_summary_generation"] = {
                "template": p2.template,
                "system_message": p2.system_message
            }
            
        with open("/Users/tavitammachintha/Desktop/UM/UM_backend/summary_prompts_backup.json", "w") as f:
            json.dump(backup_data, f, indent=4)
            
        print("Successfully backed up prompts to summary_prompts_backup.json")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    backup_prompts()
