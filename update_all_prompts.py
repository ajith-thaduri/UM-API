import os
import sys

# Add the app directory to sys.path
sys.path.append(os.getcwd())

from app.db.session import SessionLocal
from app.repositories.prompt_repository import prompt_repository

def update_all_prompts():
    db = SessionLocal()
    user_id = "00000000-0000-0000-0000-000000000000"
    
    contradiction_rule = """
CRITICAL CONTRADICTION RULE:
If a clinical finding or diagnosis has a documented discordance in the record (provided in Section 8 or the Concerns section), you MUST NOT use definitive terms like 'confirmed', 'established', 'diagnostic', or 'fixed'. In ALL narrative sections, you must describe it neutrally as 'documented discordance between [findings] and [impression]' or 'conflicting findings regarding [topic]'. Do not attempt to resolve the conflict yourself."""

    try:
        # 1. Update summary_generation
        p1_id = "summary_generation"
        p1 = prompt_repository.get_by_id(db, p1_id)
        if p1:
            new_sys = p1.system_message
            # Remove the old restriction if it still exists
            old_restriction = 'DO NOT INCLUDE: Any section about "potential missing information" or "items that may require review". Focus only on the documented clinical information.'
            new_sys = new_sys.replace(old_restriction, "").strip()
            
            # Add the Contradiction Rule
            if "CRITICAL CONTRADICTION RULE" not in new_sys:
                new_sys += "\n" + contradiction_rule
            
            # Clean up template - ensure Section 8 is clean
            new_template = p1.template
            if "8. CLINICAL CONTRADICTIONS" in new_template:
                # Ensure it's correctly labeled and has the variable
                if "{contradictions_text}" not in new_template:
                     new_template = new_template.split("8. CLINICAL CONTRADICTIONS")[0] + "8. CLINICAL CONTRADICTIONS AND INCONSISTENCIES\n{contradictions_text}"
            
            prompt_repository.update_prompt(
                db=db, prompt_id=p1_id, template=new_template, system_message=new_sys,
                user_id=user_id, change_notes="Refined Section 8 and implemented Global Contradiction Rule to improve accuracy."
            )
            print(f"Updated {p1_id}")

        # 2. Update executive_summary_generation
        p2_id = "executive_summary_generation"
        p2 = prompt_repository.get_by_id(db, p2_id)
        if p2:
            new_sys_2 = p2.system_message
            if "CRITICAL CONTRADICTION RULE" not in new_sys_2:
                new_sys_2 = new_sys_2.strip() + "\n" + contradiction_rule
            
            # Update instructions to integrate concerns
            new_template_2 = p2.template
            old_instr = "Create EXACTLY 4-6 bullet points that tell the patient's story chronologically."
            new_instr = "Create EXACTLY 4-6 bullet points that tell the patient's story chronologically. CRITICAL: Review 'POTENTIAL CONCERNS' and integrate any 'DISCORDANT DATA' into the relevant bullets (Presentation/Course) rather than resolving them."
            new_template_2 = new_template_2.replace(old_instr, new_instr)
            
            prompt_repository.update_prompt(
                db=db, prompt_id=p2_id, template=new_template_2, system_message=new_sys_2,
                user_id=user_id, change_notes="Implemented Global Contradiction Rule and integrated concerns into narrative flow."
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
    update_all_prompts()
