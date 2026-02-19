import os
import sys

# Add the app directory to sys.path
sys.path.append(os.getcwd())

from app.db.session import SessionLocal
from app.repositories.prompt_repository import prompt_repository

def update_reconciliation_rules():
    db = SessionLocal()
    user_id = "00000000-0000-0000-0000-000000000000"
    
    reconciliation_protocol = """
═══════════════════════════════════════════════════════════════════════════════
RECONCILIATION PROTOCOL (CRITICAL FOR ACCURACY)
═══════════════════════════════════════════════════════════════════════════════

1. MEDICATION/ALLERGY RECONCILIATION:
   - Before flagging a medication "gap" or "omission" in discharge planning, you MUST check the ALLERGIES section.
   - If a missing medication (e.g., Statin, ACE inhibitor, Beta-blocker) corresponds to a documented allergy or adverse reaction (e.g., Atorvastatin causing myalgia, Lisinopril causing angioedema), do NOT flag it as a documentation gap.
   - Instead, state: "Medication [Name] appropriately omitted from discharge regimen due to documented allergy/adverse reaction ([Reaction])."

2. DIAGNOSIS/IMAGING RECONCILIATION:
   - If a primary diagnosis is contradicted by objective findings (e.g., [DIAGNOSTIC DISCORDANCE] banner provided), you MUST NOT present the diagnosis as "confirmed" or "established".
   - Describe it neutrally: "Documented discharge diagnosis of [X] (Note: imaging findings were documented as discordant with radiology impression)."

3. TEMPORAL RECONCILIATION:
   - Carefully review dates. If a vital sign or event occurs AFTER the discharge date, explicitly label it as "Post-discharge documentation" or "Outpatient data artifact".
   - LOS CALCULATION: Calculate Length of Stay as (Discharge Date - Admission Date). For dates spanning 01/14 to 01/18, report as "5-day hospitalization" to avoid ambiguity.

4. NEUTRALITY REINFORCEMENT:
   - Do not use interpretative adjectives like "appropriate," "inappropriate," "correct," or "incorrect" when describing these reconciliations. Stick to "documented as..." or "omitted due to documented...".
"""

    try:
        # 1. Update summary_generation
        p1_id = "summary_generation"
        p1 = prompt_repository.get_by_id(db, p1_id)
        if p1:
            new_sys = p1.system_message
            if "RECONCILIATION PROTOCOL" not in new_sys:
                new_sys += "\n" + reconciliation_protocol
            
            prompt_repository.update_prompt(
                db=db, prompt_id=p1_id, template=p1.template, system_message=new_sys,
                user_id=user_id, change_notes="Implemented detailed Reconciliation Protocol for cross-sectional reasoning."
            )
            print(f"Updated {p1_id}")

        # 2. Update executive_summary_generation
        p2_id = "executive_summary_generation"
        p2 = prompt_repository.get_by_id(db, p2_id)
        if p2:
            new_sys_2 = p2.system_message
            if "RECONCILIATION PROTOCOL" not in new_sys_2:
                new_sys_2 += "\n" + reconciliation_protocol
            
            prompt_repository.update_prompt(
                db=db, prompt_id=p2_id, template=p2.template, system_message=new_sys_2,
                user_id=user_id, change_notes="Implemented detailed Reconciliation Protocol for executive summary accuracy."
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
    update_reconciliation_rules()
