import os
import sys
import json

# Add the app directory to sys.path
sys.path.append(os.getcwd())

from app.db.session import SessionLocal
from app.services.summary_service import summary_service
from app.services.prompt_service import prompt_service

def verify_all_prompts():
    db = SessionLocal()
    try:
        # Mock payload
        clinical_data = {
            "admission_date": "01/14/2026",
            "discharge_date": "01/18/2026",
            "diagnoses": [{"name": "Acute Pulmonary Embolism"}]
        }
        timeline = [{"date": "01/14/2026", "description": "Admission"}]
        contradictions = [
            {"description": "CT findings mention 'large saddle embolus' but impression says 'Normal'."}
        ]
        
        de_id_payload = {
            "clinical_data": clinical_data,
            "timeline": timeline,
            "red_flags": contradictions,
            "document_chunks": ["Sample doc chunk"]
        }
        
        # 1. Verify summary_generation
        print("\n=== VERIFYING summary_generation ===")
        vars1 = summary_service._build_tier2_variables_from_payload(
            de_id_payload, patient_token="[[PERSON-01]]", case_number_token="[[CASE-01]]"
        )
        p1 = prompt_service.render_prompt("summary_generation", vars1)
        sys1 = prompt_service.get_system_message("summary_generation")
        
        if "CRITICAL CONTRADICTION RULE" in sys1:
            print("SUCCESS: Contradiction Rule found in System Message.")
        else:
            print("FAILURE: Contradiction Rule MISSING from System Message.")
            
        if "• DISCORDANT DATA:" in p1:
            print("SUCCESS: High-signal banner found in Template.")
        else:
            print("FAILURE: High-signal banner MISSING from Template.")

        if 'DO NOT INCLUDE: Any section about "potential missing information"' in sys1:
             print("FAILURE: Old restriction still present in System Message.")
        else:
             print("SUCCESS: Old restriction REMOVED from System Message.")

        # 2. Verify executive_summary_generation
        print("\n=== VERIFYING executive_summary_generation ===")
        # Executive summary using _extract_key_data_for_executive
        # But we need the rendered prompt
        # We'll just check if the rule is in the system message
        sys2 = prompt_service.get_system_message("executive_summary_generation")
        if "CRITICAL CONTRADICTION RULE" in sys2:
            print("SUCCESS: Contradiction Rule found in System Message.")
        else:
            print("FAILURE: Contradiction Rule MISSING from System Message.")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    verify_all_prompts()
