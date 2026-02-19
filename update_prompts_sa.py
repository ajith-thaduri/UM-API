import os
import sys

# Add the app directory to sys.path
sys.path.append(os.getcwd())

from app.db.session import SessionLocal
from app.repositories.prompt_repository import prompt_repository

def update_prompt():
    db = SessionLocal()
    try:
        p_id = "summary_generation"
        p = prompt_repository.get_by_id(db, p_id)
        if not p:
            print(f"Prompt {p_id} NOT FOUND")
            return

        # 1. Update System Message
        new_sys = p.system_message
        # Remove the restriction
        old_restriction = 'DO NOT INCLUDE: Any section about "potential missing information" or "items that may require review". Focus only on the documented clinical information.'
        if old_restriction in new_sys:
            new_sys = new_sys.replace(old_restriction, "")
        else:
            print("Warning: Restriction string not found exactly as expected.")

        # Update Section 8 instructions
        section_8_instr = """
8. CLINICAL CONTRADICTIONS AND INCONSISTENCIES:
   - Document any clinical discrepancies, discordant findings, or temporal inconsistencies found in the record.
   - Present these as a factual narrative (e.g., "The record contains discordant findings regarding...").
   - Be specific but concise. 
   - If no inconsistencies are identified, state: "No significant clinical contradictions or inconsistencies were identified in the available documentation."
   - This section is mandatory for the clinical summary.
"""
        # Append before formatting or at the end
        if "7. PROCEDURES PERFORMED" in new_sys:
            # Insert after section 7
            parts = new_sys.split('7. PROCEDURES PERFORMED')
            # we need to find the end of 7. Actually easier to just append before the next major block or end
            new_sys = new_sys.strip() + "\n" + section_8_instr
        
        # 2. Update Template
        new_template = p.template
        if "7. PROCEDURES PERFORMED" in new_template:
            section_8_template = "\n\n8. CLINICAL CONTRADICTIONS AND INCONSISTENCIES\n{contradictions_text}"
            if "8. CLINICAL CONTRADICTIONS" not in new_template:
                new_template = new_template.strip() + section_8_template

        # Update the prompt
        # Note: prompt_repository.update_prompt requires user_id and change_notes
        updated = prompt_repository.update_prompt(
            db=db,
            prompt_id=p_id,
            template=new_template,
            system_message=new_sys,
            user_id="00000000-0000-0000-0000-000000000000",
            change_notes="Added clinical contradictions section as the final field (Section 8) to improve accuracy and highlight discrepancies."
        )
        
        if updated:
            print(f"Successfully updated prompt: {p_id}")
            # Also clear cache in prompt_service
            from app.services.prompt_service import prompt_service
            prompt_service.refresh_cache()
        else:
            print(f"Failed to update prompt: {p_id}")

    except Exception as e:
        print(f"Error: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    update_prompt()
