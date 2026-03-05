import json
import logging
from app.services.presidio.service import presidio_deidentification_service


test_text = """Patient Name: Henry Jonathan Matthews
Alias Name: Johnny Matthews
Gender: Male

Date of Birth: March 14, 1985
Age: 39

Social Security Number: 547-82-1934

Driver License Number: CA-DL-84739201

Passport Number: XK9384721

Medical Record Number (MRN): MRN-88392011

Account Number: ACC-55271892

Health Plan Beneficiary Number: HPB-882718

Insurance Provider: BlueCross BlueShield

Employer Name: TechNova Systems Inc

CONTACT INFORMATION

Mobile Phone: +1-217-555-8934

Home Phone: +1-217-555-1221

Email Address:
henry.matthews85@gmail.com

Patient Portal Username:
hmatthews_85

Patient Portal URL:
https://patientportal.midwesthealth.org/login

Emergency Contact:

Name: Emily Matthews
Relationship: Spouse
Phone: +1-217-555-7743

HOME ADDRESS

742 Evergreen Terrace
Apartment 5B

Room 312

Suite 210

Springfield, Illinois
ZIP Code: 62704

County: Sangamon County

State: Illinois

Country: United States

DEVICE & NETWORK INFORMATION

MAC Address:
00:1A:2B:3C:4D:5E

IP Address:
192.168.44.212

Device ID:
DEV-8827391

Browser Fingerprint ID:
BF-928374923

Face Scan ID:
FACESCAN-8821-9932

Biometric Authentication Token:
BIO-22918772

VEHICLE INFORMATION

Primary Vehicle

Vehicle Owner: Henry Jonathan Matthews

Vehicle Make: Toyota

Vehicle Model: Camry

Vehicle Year: 2021

Vehicle Color: Silver

License Plate Number: IL-8721-KD

Vehicle Identification Number (VIN):
4T1BF1FK5HU382917

Parking Permit ID: PP-88291

PAYMENT INFORMATION

Credit Card Holder: Henry Jonathan Matthews

Card Number: 4111-9283-8812-7721

Expiration Date: 08/27

CVV: 739

Billing Address:

742 Evergreen Terrace
Apartment 5B
Springfield, Illinois 62704
United States

HOSPITAL VISIT INFORMATION

Hospital Name: Springfield Regional Medical Center

Hospital Address:

800 Medical Plaza Drive
Suite 400

Springfield, Illinois 62703
United States

Attending Physician: Dr. Michael Anderson

Physician NPI: NPI-99288211

Visit Date: February 11, 2025

Admission Date: February 11, 2025

Discharge Date: February 14, 2025

Room Number: Room 412

Bed Number: Bed B

CLINICAL NOTES

Patient Henry Jonathan Matthews, also known by alias Johnny Matthews, presented with symptoms of chest discomfort and shortness of breath.

The patient confirmed his identity using the hospital biometric authentication system with Face Scan ID FACESCAN-8821-9932.

The patient accessed the medical report through the hospital portal using the username hmatthews_85 via the secure portal link:

https://patientportal.midwesthealth.org/login

The patient works as a Senior Software Engineer at TechNova Systems Inc located in Chicago, Illinois.

LAB & TEST INFORMATION

Lab Order ID: LAB-88217

Sample ID: SMP-77128

Test Date: February 12, 2025

Laboratory Facility:

Midwest Diagnostic Labs
1200 Health Park Drive
Suite 310

Chicago, Illinois
United States

INSURANCE CLAIM INFORMATION

Policy Number: POL-8821782

Claim Number: CLM-889921

Health Plan: BlueCross BlueShield

Employer: TechNova Systems Inc

Group ID: GRP-22911

DISCHARGE SUMMARY

Patient Henry Jonathan Matthews was discharged on February 14, 2025 in stable condition.

Discharge Instructions were sent to the patient's registered email henry.matthews85@gmail.com
 and made available through the patient portal.

The patient was advised to schedule a follow-up appointment within two weeks."""

class MockDB:
    def query(self, *args):
        class MockQuery:
            def filter(self, *args, **kwargs): return self
            def all(self): return []
        return MockQuery()
    def flush(self): pass
    def add(self, *args): pass
    def commit(self): pass
    def refresh(self, obj): obj.id = "test-vault-id"
    def close(self): pass

def main():
    db = MockDB()
    try:
        case_id = "test_case_comprehensive_001"
        user_id = "test_user_001"
        patient_name = "Henry Jonathan Matthews"
        
        clinical_data = {}
        timeline = []
        red_flags = []
        
        case_metadata = {
            "Alias Used in Prior Records": "Johnny Matthews",
            "emergency_contact": "Emily Matthews",
            "mrn": "MRN-88392011",
            "ssn": "547-82-1934",
            "provider": "Dr. Michael Anderson",
            "facility": "Springfield Regional Medical Center",
            "insurance_provider": "BlueCross BlueShield",
            "employer": "TechNova Systems Inc",
            "account_number": "ACC-55271892",
            "phone": "+1-217-555-8934",
            "email": "henry.matthews85@gmail.com",
        }
        
        document_chunks = [test_text]
        
        import app.services.presidio.service
        app.services.presidio.service.settings.ENABLE_PREFLIGHT_VALIDATION = False
        
        payload, vault_id, token_map = presidio_deidentification_service.de_identify_for_summary(
            db=db,
            case_id=case_id,
            user_id=user_id,
            patient_name=patient_name,
            timeline=timeline,
            clinical_data=clinical_data,
            red_flags=red_flags,
            case_metadata=case_metadata,
            document_chunks=document_chunks
        )
        
        print("\n=== DE-IDENTIFIED TEXT ===")
        print(payload["document_chunks"][0])
        print("\n=== TOKEN MAP ===")
        print(json.dumps(token_map, indent=2))
        
    finally:
        db.close()

if __name__ == "__main__":
    main()
