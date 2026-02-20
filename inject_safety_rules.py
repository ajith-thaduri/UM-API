import os
import sys

# Add the app directory to sys.path
sys.path.append(os.getcwd())

from app.db.session import SessionLocal
from app.repositories.prompt_repository import prompt_repository

def inject_safety_rules():
    db = SessionLocal()
    user_id = "00000000-0000-0000-0000-000000000000"
    
    safety_rules = """

STRICT DOCUMENTATION SAFETY RULES (MANDATORY)
1. Do NOT convert Day index to calendar date unless explicitly written in the source document.
2. Do NOT state exact medication dose, frequency, route, or timing unless documented verbatim in the source.
3. Do NOT convert modeled prediction, risk projection, or forward-looking analysis into confirmed clinical outcomes.
4. Do NOT convert an "assessment," "screening," or "evaluation" into a confirmed diagnosis or event.
5. Do NOT claim duration of follow-up (e.g., 30-day, 6-month) unless explicitly documented as completed follow-up.
6. Do NOT derive calculated values (LOS, % decline, timeline math) unless explicitly stated.
7. If uncertain, state: "Not explicitly documented."
8. When in doubt between explicit documentation and reasonable inference, default to explicit documentation only."""

    try:
        # 1. Update summary_generation
        p1_id = "summary_generation"
        p1 = prompt_repository.get_by_id(db, p1_id)
        if p1:
            new_sys = p1.system_message
            if "STRICT DOCUMENTATION SAFETY RULES" not in new_sys:
                new_sys += safety_rules
            
            prompt_repository.update_prompt(
                db=db, prompt_id=p1_id, template=p1.template, system_message=new_sys,
                user_id=user_id, change_notes="Injecting Strict Documentation Safety Rules for 1000+ page accuracy."
            )
            print(f"Updated {p1_id}")

        # 2. Update executive_summary_generation
        p2_id = "executive_summary_generation"
        p2 = prompt_repository.get_by_id(db, p2_id)
        if p2:
            new_sys_2 = p2.system_message
            if "STRICT DOCUMENTATION SAFETY RULES" not in new_sys_2:
                new_sys_2 += safety_rules
            
            prompt_repository.update_prompt(
                db=db, prompt_id=p2_id, template=p2.template, system_message=new_sys_2,
                user_id=user_id, change_notes="Injecting Strict Documentation Safety Rules for executive summary."
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
    inject_safety_rules()
