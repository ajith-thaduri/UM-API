import os
import sys

# Add the app directory to sys.path
sys.path.append(os.getcwd())

from app.db.session import SessionLocal
from app.repositories.prompt_repository import prompt_repository

def update_prohibit_json():
    db = SessionLocal()
    user_id = "00000000-0000-0000-0000-000000000000"
    
    no_json_rule = "\n\nCRITICAL: DO NOT OUTPUT JSON. PROVIDE ONLY HUMAN-READABLE MARKDOWN TEXT. START DIRECTLY WITH THE SUMMARY CONTENT."

    try:
        # 1. Update summary_generation
        p1_id = "summary_generation"
        p1 = prompt_repository.get_by_id(db, p1_id)
        if p1:
            new_sys = p1.system_message
            if "DO NOT OUTPUT JSON" not in new_sys:
                new_sys += no_json_rule
            
            prompt_repository.update_prompt(
                db=db, prompt_id=p1_id, template=p1.template, system_message=new_sys,
                user_id=user_id, change_notes="Explicitly prohibiting JSON to fix frontend rendering."
            )
            print(f"Updated {p1_id}")

        # 2. Update executive_summary_generation
        p2_id = "executive_summary_generation"
        p2 = prompt_repository.get_by_id(db, p2_id)
        if p2:
            new_sys_2 = p2.system_message
            if "DO NOT OUTPUT JSON" not in new_sys_2:
                new_sys_2 += no_json_rule
            
            prompt_repository.update_prompt(
                db=db, prompt_id=p2_id, template=p2.template, system_message=new_sys_2,
                user_id=user_id, change_notes="Explicitly prohibiting JSON for executive summary."
            )
            print(f"Updated {p2_id}")

        # Clear cache
        from app.services.prompt_service import prompt_service
        prompt_service.refresh_cache()
        print("Done.")

    except Exception as e:
        print(f"Error: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    update_prohibit_json()
