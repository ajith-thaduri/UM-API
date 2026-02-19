import os
import sys
import json

# Add the app directory to sys.path
sys.path.append(os.getcwd())

from app.db.session import SessionLocal
from app.services.summary_service import summary_service
from app.services.prompt_service import prompt_service

def verify_contradiction_rendering():
    db = SessionLocal()
    try:
        # 1. Prepare mock data mimicking the Leo Martinez case
        patient_name = "Leo Martinez"
        case_number = "UM-458392"
        
        clinical_data = {
            "admission_date": "01/14/2026",
            "discharge_date": "01/18/2026",
            "diagnoses": [{"name": "Acute Respiratory Failure"}, {"name": "Hypotension"}],
            "medications": [
                {"name": "Lisinopril", "dosage": "10mg", "frequency": "Daily"},
                {"name": "Atorvastatin", "dosage": "20mg", "frequency": "Daily"}
            ],
            "allergies": [
                {"allergen": "Lisinopril", "reaction": "Angioedema"},
                {"allergen": "Atorvastatin", "reaction": "Myalgia"}
            ]
        }
        
        timeline = [
            {"date": "01/14/2026", "description": "Patient admitted with shortness of breath", "event_type": "admission"},
            {"date": "01/19/2026", "description": "Vitals: BP 110/70, HR 82", "event_type": "vitals"}, # Post-discharge
            {"date": "01/18/2026", "description": "Patient discharged to home", "event_type": "discharge"}
        ]
        
        contradictions = [
            {
                "type": "radiology_inconsistency",
                "description": "Potential Radiology Inconsistency: CT findings mention 'large saddle embolus' but impression suggests 'Normal CT Angiogram'."
            },
            {
                "type": "clinical_conflict",
                "description": "Potential Safety Alert: Medication 'Lisinopril' documented while patient has allergy to 'lisinopril'."
            },
            {
                "type": "chronological_error",
                "description": "Impossible sequence: Vitals documented on 01/19/2026 is after Discharge on 01/18/2026."
            }
        ]
        
        # 2. Build variables
        # Note: _build_tier2_variables_from_payload expects de_id_payload
        de_id_payload = {
            "clinical_data": clinical_data,
            "timeline": timeline,
            "red_flags": contradictions,
            "document_chunks": ["Sample doc chunk 1", "Sample doc chunk 2"]
        }
        
        variables = summary_service._build_tier2_variables_from_payload(
            de_id_payload=de_id_payload,
            patient_token="[[PERSON-01]]",
            case_number_token="[[CASE-01]]"
        )
        
        # 3. Render prompt
        prompt_id = "summary_generation"
        rendered_prompt = prompt_service.render_prompt(prompt_id, variables)
        
        # 4. Check for Section 8
        print("\n=== VERIFICATION RESULTS ===")
        if "8. CLINICAL CONTRADICTIONS AND INCONSISTENCIES" in rendered_prompt:
            print("SUCCESS: Section 8 header found in rendered prompt.")
        else:
            print("FAILURE: Section 8 header NOT found.")
            
        print("\n--- Rendered Section 8 Content ---")
        section_start = rendered_prompt.find("8. CLINICAL CONTRADICTIONS")
        print(rendered_prompt[section_start:])
        
        # Verify the specific data is there
        if "large saddle embolus" in rendered_prompt and "Lisinopril" in rendered_prompt:
            print("\nSUCCESS: Contradiction descriptions are correctly rendered.")
        else:
            print("\nFAILURE: Contradiction descriptions missing from prompt.")

    except Exception as e:
        print(f"Error during verification: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    verify_contradiction_rendering()
