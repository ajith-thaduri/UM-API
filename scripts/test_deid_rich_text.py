import asyncio
import json
import sys
import os

# Add UM-API to sys.path
sys.path.append("/Users/ajiththaduri/Desktop/V2/UM-API")

from app.services.presidio_deidentification_service import presidio_deidentification_service
from app.core.config import settings
from sqlalchemy.orm import Session
from app.db.session import SessionLocal

TEST_TEXT = """
CASE METADATA

Patient Name: John Michael Doe
Alias Used in Prior Records: Johnny Doe
Date of Birth: 03/14/1980
SSN: 123-45-6789
Medical Record Number (MRN): 000123456
Case Number: BC-2025-000123456
Health Plan ID: HP-9988776655
Account Number: ACC-55667788
NPI (Attending): 1548273645

Address:
742 Evergreen Terrace
Springfield, IL 62704

Phone (Home): (217) 555-7890
Phone (Mobile): (217) 555-1122
Email: john.doe@email.com

Secondary Email: jdoe1980@gmail.com

Emergency Contact:
Jane Doe (Spouse)
Phone: (217) 555-3344
Email: jane.doe@email.com

ADMISSION RECORD

John Michael Doe was admitted to St. Mary’s Regional Medical Center on 03/02/2025 under the care of Dr. Michael Smith, MD (NPI: 1548273645).

John Michael Doe presented with shortness of breath and chest tightness. Johnny Doe reports worsening dyspnea for 3 days.

MRN 000123456 confirms prior visit in 2023 for hypertension.

Admission Date: 03/02/2025
Discharge Date: 03/09/2025

CHIEF COMPLAINT

“Shortness of breath and chest pressure.”

John Michael Doe states that he, John Doe, began experiencing symptoms while at home at 742 Evergreen Terrace, Springfield, IL.

HISTORY OF PRESENT ILLNESS

John Michael Doe (DOB 03/14/1980) reports:

Progressive dyspnea

Orthopnea

Mild bilateral leg swelling

He denies fever. He denies recent travel outside Illinois.

He confirms that his phone number is (217) 555-7890 and requests contact via john.doe@email.com
.

PAST MEDICAL HISTORY

Hypertension

Type 2 Diabetes Mellitus

Hyperlipidemia

Prior admission in 2023 (same MRN: 000123456)

MEDICATIONS

Lisinopril 20 mg daily

Metformin 1000 mg BID

Atorvastatin 40 mg nightly

Pharmacy on file:
CVS Pharmacy
123 Main Street
Springfield, IL 62704
Phone: (217) 555-7788

ALLERGIES

Penicillin (rash)

VITALS (03/02/2025)

BP: 168/94

HR: 104

Temp: 98.6°F

RR: 22

SpO2: 89% RA

LAB RESULTS
Date	Test	Result	Flag
03/02/2025	WBC	14.2 K/µL	High
03/02/2025	BNP	980 pg/mL	High
03/04/2025	Creatinine	1.8 mg/dL	Elevated
IMAGING

03/03/2025 – CT Chest
Findings consistent with pulmonary edema.

03/03/2025 – Chest X-Ray
Cardiomegaly present.

PROCEDURES

03/04/2025 – Echocardiogram
EF 35%

THERAPY NOTES

Physical therapy evaluation 03/06/2025:
Patient John Michael Doe ambulated 25 feet with assistance.

SOCIAL HISTORY

John Michael Doe lives with spouse Jane Doe at 742 Evergreen Terrace.

Employment:
Works at Springfield Nuclear Power Plant
Employer ID: EMP-887766

Insurance:
Blue Cross Blue Shield of Illinois
Policy Number: BCBS-4433221100

DISCHARGE SUMMARY

John Michael Doe was discharged home on 03/09/2025.

Follow-up appointment scheduled with:
Dr. Michael Smith
Email: msmith@stmarys.org

Phone: (217) 555-9900

Discharge Instructions emailed to john.doe@email.com
 and jdoe1980@gmail.com
.

FOLLOW-UP NOTE (OUTPATIENT)

Date: 03/20/2025

Johnny Doe reports improvement.
Blood pressure controlled.

Dr. Michael Smith documents continued monitoring.

CONTRADICTION TEST SECTION

NOTE A:
"Patient John Michael Doe has no known history of diabetes."

NOTE B:
"Past Medical History includes Type 2 Diabetes Mellitus."

ADDITIONAL PII EDGE CASES

IP Address: 192.168.1.45

Device ID: DEV-1122334455

Driver’s License: D1234567 (Illinois)

Vehicle Plate: IL-ABC-7890

Passport: X12345678

Fax: (217) 555-2233

Website: www.johndoehealthrecords.com

REPEATED PHI STRESS SECTION

John Michael Doe
John Michael Doe
John Michael Doe
Johnny Doe
Johnny Doe

john.doe@email.com

john.doe@email.com

jdoe1980@gmail.com

jdoe1980@gmail.com

(217) 555-7890
(217) 555-7890

000123456
000123456
000123456

03/02/2025
03/02/2025
03/09/2025
03/09/2025
"""

async def run_test():
    # Use a mock session and bypass DB writes
    from unittest.mock import MagicMock
    db = MagicMock()
    
    case_id = "test-case-id"
    user_id = "test-user-id"
    patient_name = "John Michael Doe"
    
    metadata = {
        "case_number": "BC-2025-000123456",
        "ssn": "123-45-6789",
        "mrn": "000123456",
        "facility": "St. Mary’s Regional Medical Center",
        "provider": "Dr. Michael Smith",
        "Alias Used in Prior Records": "Johnny",
        "emergency_contact_name": "Jane Doe"
    }

    print("--- STARTING DE-IDENTIFICATION TEST ---")
    
    # We use a mock clinical data and timeline to test the whole pipeline
    clinical_data = {
        "summary": TEST_TEXT,
        "history": "Prior visit in 2023 for hypertension."
    }
    timeline = [
        {"date": "03/02/2025", "description": "Admitted to St. Mary's"}
    ]
    red_flags = []
    
    # Bypass DB commit/refresh
    db.commit = MagicMock()
    db.add = MagicMock()
    db.refresh = MagicMock()

    try:
        # We manually call de_identify_for_summary to avoid async thread pool issues in a simple script if needed
        # but let's try the async version first
        de_id_payload, vault_id, token_map = await presidio_deidentification_service.de_identify_for_summary_async(
            db=db,
            case_id=case_id,
            user_id=user_id,
            patient_name=patient_name,
            timeline=timeline,
            clinical_data=clinical_data,
            red_flags=red_flags,
            case_metadata=metadata,
            document_chunks=[TEST_TEXT]
        )
        
        print("\n--- TOKEN MAP ---")
        for token, original in sorted(token_map.items()):
            print(f"{token}: {original}")
            
        print("\n--- DE-IDENTIFIED PAYLOAD (Sample) ---")
        # Print first 1000 chars of de-identified text
        summary_text = de_id_payload["clinical_data"]["summary"]
        print(summary_text[:1000] + "...")
        
        print("\n--- CHECKING FOR LEAKS ---")
        leaks_found = []
        for val in token_map.values():
            if not val or len(val) < 3: continue # skip empty or tiny strings
            if val in summary_text:
                leaks_found.append(val)
        
        if leaks_found:
            print(f"FAILED: Found following values in de-identified text: {leaks_found}")
        else:
            print("SUCCESS: No known PHI leaks found in summary text.")

        # Check for date shifts
        print("\n--- DATE SHIFTS ---")
        # Find some dates in original text and see if they are gone
        original_dates = ["03/02/2025", "03/14/1980", "03/20/2025"]
        any_date_leak = False
        for od in original_dates:
            if od in summary_text:
                print(f"FAILED: Date {od} was not shifted.")
                any_date_leak = True
        
        if not any_date_leak:
            print("SUCCESS: Dates appear to be shifted.")

    except Exception as e:
        print(f"Error during test: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(run_test())
