
import asyncio
import os
import sys
import uuid
from datetime import datetime

# Add the project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.presidio import presidio_deidentification_service
from app.db.session import SessionLocal
from app.models.case import Case, CaseStatus
from app.models.user import User

TEST_DOCUMENT = """
Patient Name: Daniel Christopher Mitchell
Alias: Dan Mitchell
Gender: Male

Date of Birth: September 18, 1982
Age: 42

Social Security Number: 623-44-9182

Medical Record Number (MRN): MRN-88392011

Patient Account Number: ACC-55271892

Health Insurance Policy Number: HLT-993821771

Insurance Provider: BlueCross BlueShield

Driver License Number: CA-DL-88327411

Passport Number: XZ8829134

Biometric Identifiers
Fingerprint ID: FP-77381921
Retina Scan ID: RET-8829101
Face Scan ID: FACE-992811

Contact Information

Home Address:
4587 Pinecrest Drive
Apartment 12B
San Diego, California 92103
United States

Previous Address:
742 Evergreen Terrace
Springfield, Illinois 62704

Phone Number: +1-619-555-7712

Alternate Phone: (619) 555-1182

Fax Number: +1-619-555-4422

Email Address: daniel.mitchell82@gmail.com

Work Email: dmitchell@pacificfinancegroup.com

Employer Information

Employer: Pacific Finance Group

Employee ID: EMP-883992

Office Address:
1200 Market Street, Suite 440
San Francisco, CA 94105

Emergency Contact

Name: Rebecca Mitchell
Relationship: Spouse
Phone: +1-619-555-9001
Email: rebecca.mitchell.family@gmail.com

Financial Information

Credit Card Number:
4532 8890 1123 7789

Bank Account Number:
ACCT-772188293

Routing Number:
121000248

Billing Account Number:
BILL-88372119

Medical Encounter Details

Hospital Name: West Coast Medical Center

Hospital Address:
1550 Health Plaza Drive
San Diego, CA 92123

Attending Physician:
Dr. Michael Thompson

Referring Physician:
Dr. Sarah Patel

Primary Nurse:
Jennifer Collins RN

Admission Date: February 10, 2025

Discharge Date: February 14, 2025

Follow-up Appointment: March 20, 2025

Appointment Time: 10:30 AM

Medical Identifiers

Encounter ID: ENC-99218823

Prescription Number: RX-88219321

Laboratory Accession Number: LAB-99218832

Radiology Report ID: RAD-77382911

Device and Network Identifiers

Patient Portal Username: daniel.mitchell82

Patient Portal URL:
https://portal.westcoastmedical.org/patientrecords

Login IP Address:
192.168.10.45

Device ID:
DEVICE-882199

MAC Address:
00:1A:2B:3C:4D:5E

Vehicle Information

Vehicle License Plate: CA-7XK-8821

Vehicle VIN: 1HGCM82633A004352

Parking Permit Number: PP-883211

Online References

Personal Website:
http://www.danielmitchellhealthrecords.com

LinkedIn Profile:
https://linkedin.com/in/daniel-mitchell-1982

Notes

Patient Daniel Christopher Mitchell reported severe chest pain and dizziness.
Dr. Michael Thompson ordered ECG and blood work.

Billing will be processed through insurance policy HLT-993821771 and remaining balance will be charged to billing account BILL-88372119.
"""

async def run_test():
    db = SessionLocal()
    case_id = f"test-presidio-{str(uuid.uuid4())[:8]}"
    user_id = "00000000-0000-0000-0000-000000000000"
    
    try:
        # Create a temporary case to satisfy foreign key
        new_case = Case(
            id=case_id,
            patient_id="test-patient-id",
            patient_name="Daniel Christopher Mitchell",
            case_number=f"TEST-PN-{str(uuid.uuid4())[:8]}",
            status=CaseStatus.UPLOADED,
            user_id=user_id,
        )
        db.add(new_case)
        db.commit()
        
        patient_name = "Daniel Christopher Mitchell"
        clinical_data = {}
        timeline = []
        red_flags = []
        document_chunks = [TEST_DOCUMENT]
        
        print("\n" + "="*80)
        print("  PRESIDIO COMPREHENSIVE HIPAA STRESS TEST  ")
        print("="*80)
        
        print(f"\n[STEP 1] Running De-Identification for Case {case_id}...")
        # Since we use the async wrapper, we can't easily see intermediate state 
        # unless we modify the service itself. I'll just run it and see.
        payload, vault_id, token_map = await presidio_deidentification_service.de_identify_for_summary_async(
            db=db,
            case_id=case_id,
            user_id=user_id,
            patient_name=patient_name,
            timeline=timeline,
            clinical_data=clinical_data,
            red_flags=red_flags,
            document_chunks=document_chunks
        )
        
        de_id_text = payload["document_chunks"][0]
        
        print("\n--- DE-IDENTIFIED DOCUMENT ---")
        print(de_id_text)
        
        print("\n" + "-"*40)
        print(f"VAULT ID: {vault_id}")
        print(f"TOKENS GENERATED: {len(token_map)}")
        print("-"*40)
        
        print("\n--- DETECTED TOKENS (SAMPLE) ---")
        sorted_tokens = sorted(token_map.items(), key=lambda x: x[0])
        for token, original in sorted_tokens[:20]:
            print(f"  {token}: {original}")
        if len(sorted_tokens) > 20:
            print(f"  ... and {len(sorted_tokens) - 20} more.")
            
        print("\n[STEP 2] Verifying Re-identification...")
        re_id_text = await presidio_deidentification_service.re_identify_summary_async(
            db=db,
            vault_id=vault_id,
            summary_text=de_id_text
        )
        
        # Check if dates were shifted (they should be shifted in de_id, and then shifted back in re_id)
        # Note: exactly matching the original document might fail if there are overlapping patterns
        # or if Presidio modified the text structure (unlikely with replace operator).
        
        # Print a small section to verify re-id
        print("\n--- RE-IDENTIFIED SAMPLE (Admission Date) ---")
        adm_pattern = r"Admission Date: .*"
        match_orig = re.search(adm_pattern, TEST_DOCUMENT)
        match_deid = re.search(adm_pattern, de_id_text)
        match_reid = re.search(adm_pattern, re_id_text)
        
        if match_orig: print(f"ORIG: {match_orig.group(0)}")
        if match_deid: print(f"DEID: {match_deid.group(0)}")
        if match_reid: print(f"REID: {match_reid.group(0)}")

        print("\n" + "="*80)
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Cleanup
        try:
            db.query(Case).filter(Case.id == case_id).delete()
            db.commit()
        except:
            pass
        db.close()

import re
if __name__ == "__main__":
    asyncio.run(run_test())
