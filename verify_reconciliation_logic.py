import os
import sys

# Add the app directory to sys.path
sys.path.append(os.getcwd())

from app.db.session import SessionLocal
from app.services.summary_service import summary_service
from app.services.prompt_service import prompt_service

def verify_reconciliation():
    db = SessionLocal()
    try:
        # Mock payload specifically reflecting the Leo Martinez issues
        clinical_data = {
            "admission_date": "01/14/2026",
            "discharge_date": "01/18/2026",
            "diagnoses": [{"name": "Acute Pulmonary Embolism"}, {"name": "Essential Hypertension"}],
            "medications": [{"name": "Metformin", "dosage": "500 mg", "frequency": "BID"}], # Metformin only at discharge
            "allergies": [
                {"allergen": "Lisinopril", "reaction": "Angioedema"},
                {"allergen": "Atorvastatin", "reaction": "Severe myalgia"}
            ]
        }
        timeline = [{"date": "01/14/2026", "description": "Admission"}]
        
        # Categorized contradictions as they would now be produced by summary_service
        contradictions = [
            {
                "type": "radiology_inconsistency",
                "description": "CT findings show large saddle embolus but impression says normal."
            },
            {
                "type": "clinical_conflict",
                "description": "Medication Lisinopril documented while patient has allergy to lisinopril."
            },
            {
                "type": "chronological_error",
                "description": "Vitals documented on 01/20/2026 after discharge on 01/18/2026."
            }
        ]
        
        de_id_payload = {
            "clinical_data": clinical_data,
            "timeline": timeline,
            "red_flags": contradictions,
            "document_chunks": ["Sample doc chunk"]
        }
        
        # 1. Verify Banners in summary_service
        print("\n=== VERIFYING FORMATTED BANNERS ===")
        formatted_contradictions = summary_service._format_contradictions_for_prompt(contradictions)
        print(formatted_contradictions)
        
        if "[DIAGNOSTIC DISCORDANCE]" in formatted_contradictions and "[SAFETY ALERT" in formatted_contradictions:
            print("SUCCESS: Categorized banners correctly generated.")
        else:
            print("FAILURE: Categorized banners missing.")

        # 2. Verify Reconciliation Protocol in Prompt
        print("\n=== VERIFYING RECONCILIATION PROTOCOL IN RENDERED PROMPT ===")
        vars = summary_service._build_tier2_variables_from_payload(
            de_id_payload, patient_token="[[PERSON-01]]", case_number_token="[[CASE-01]]"
        )
        sys_msg = prompt_service.get_system_message("summary_generation")
        
        if "RECONCILIATION PROTOCOL" in sys_msg:
            print("SUCCESS: Reconciliation Protocol found in System Message.")
            if "MEDICATION/ALLERGY RECONCILIATION" in sys_msg and "DIAGNOSIS/IMAGING RECONCILIATION" in sys_msg:
                 print("SUCCESS: Specific reconciliation rules (Med/Allergy, Dx/Imaging) are present.")
        else:
            print("FAILURE: Reconciliation Protocol missing from System Message.")

        # 3. Check for LOS instruction
        if "LOS CALCULATION" in sys_msg:
            print("SUCCESS: LOS Calculation instruction found.")
        else:
            print("FAILURE: LOS Calculation instruction missing.")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    verify_reconciliation()
