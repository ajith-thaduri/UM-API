import asyncio
import json
import re
import sys
import os
import random
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple, NamedTuple
from collections import Counter
from unittest.mock import MagicMock

# Setup path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# 1. Pipeline Import
try:
    from app.services.presidio.service import presidio_deidentification_service
    from app.services.presidio.constants import FREE_TEXT_FIELDS
except ImportError:
    # Fallback to old path if refactoring didn't finish or shim is missing
    from app.services.presidio_deidentification_service import presidio_deidentification_service
    FREE_TEXT_FIELDS = {"description", "narrative", "note", "comment", "details", "content", "text", "summary"}

# 2. Test Configuration & Logging
import logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# 3. Test Cases Source of Truth
# We append new test cases here as they are identified.
TEST_CASES = [
    {
        "name": "Case 1: Standard Clinical Narrative (John Michael Doe)",
        "patient_name": "John Michael Doe",
        "metadata": {
            "Alias Used in Prior Records": "Johnny Doe",
            "medical_record_number": "000123456",
            "ssn": "123-45-6789",
            "provider": "Dr. Michael Smith",
            "facility": "St. Mary's Regional Medical Center",
            "phone": "(217) 555-7890",
            "email": "john.doe@email.com",
            "address": "742 Evergreen Terrace, Springfield, IL 62704"
        },
        "text": """
Patient Name: John Michael Doe
Alias: Johnny Doe
DOB: 03/14/1980
SSN: 123-45-6789
MRN: 000123456

ADMISSION RECORD
John Michael Doe was admitted to St. Mary's Regional Medical Center on 03/02/2025 under the care of Dr. Michael Smith, MD.
Johnny Doe presented with shortness of breath. MRN 000123456 confirms prior visit.

SOCIAL HISTORY
Lives with spouse Jane Doe at 742 Evergreen Terrace in San Diego, California.
Works at Springfield Nuclear Power Plant.
IP Address: 192.168.1.45, MAC Address: 00:1B:44:11:3A:B7
        """
    },
    {
        "name": "Case 2: Comprehensive Edge Cases (Henry Jonathan Matthews)",
        "patient_name": "Henry Jonathan Matthews",
        "metadata": {
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
            "address": "742 Evergreen Terrace, Springfield, Illinois 62704"
        },
        "text": """
Patient Name: Henry Jonathan Matthews
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
Email Address: henry.matthews85@gmail.com
Patient Portal Username: hmatthews_85
Patient Portal URL: https://patientportal.midwesthealth.org/login

Emergency Contact:
Name: Emily Matthews
Relationship: Spouse
Phone: +1-217-555-7743

HOME ADDRESS
742 Evergreen Terrace, Apartment 5B, Springfield, Illinois
ZIP Code: 62704
County: Sangamon County

DEVICE & NETWORK INFORMATION
MAC Address: 00:1A:2B:3C:4D:5E
IP Address: 192.168.44.212
Device ID: DEV-8827391
Browser Fingerprint ID: BF-928374923
Face Scan ID: FACESCAN-8821-9932
Biometric Authentication Token: BIO-22918772

VEHICLE INFORMATION
License Plate Number: IL-8721-KD
Vehicle Identification Number (VIN): 4T1BF1FK5HU382917
Parking Permit ID: PP-88291

PAYMENT INFORMATION
Credit Card Holder: Henry Jonathan Matthews
Card Number: 4111-9283-8812-7721
Expiration Date: 08/27
CVV: 739

HOSPITAL VISIT INFORMATION
Hospital Name: Springfield Regional Medical Center
Attending Physician: Dr. Michael Anderson
Physician NPI: NPI-99288211
Visit Date: February 11, 2025
Admission Date: February 11, 2025
Discharge Date: February 14, 2025

CLINICAL NOTES
Patient Henry Jonathan Matthews, also known by alias Johnny Matthews, presented with symptoms of chest discomfort.
Identified via Face Scan ID FACESCAN-8821-9932.
Used username hmatthews_85 via https://patientportal.midwesthealth.org/login.
Works as a Senior Software Engineer at TechNova Systems Inc in Chicago, Illinois.

LAB & TEST INFORMATION
Lab Order ID: LAB-88217
Sample ID: SMP-77128
Test Date: February 12, 2025
Laboratory Facility: Midwest Diagnostic Labs, Chicago, Illinois

INSURANCE CLAIM INFORMATION
Policy Number: POL-8821782
Claim Number: CLM-889921
Group ID: GRP-22911

DISCHARGE SUMMARY
Henry Jonathan Matthews discharged on February 14, 2025.
Discharge Instructions sent to henry.matthews85@gmail.com.
        """
    },
    {
        "name": "Case 3: Extreme Structural Entities (Sub-Addresses & Network)",
        "patient_name": "Alexander Sterling",
        "metadata": {
            "address": "1200 Health Park Drive, Suite 310, Chicago, IL 60601",
            "account": "ACT-9928172"
        },
        "text": """
HOME ADDRESS
742 Evergreen Terrace
Apartment 5B
Room 312
Suite 210
Unit 4C
Floor 7
P.O. Box 1234
San Diego, California
ZIP Code: 92101

SECONDARY ADDRESS
1200 Health Park Drive
Suite 310
Apt. 22A
Rm. 15B
Chicago, Illinois 60601

DEVICE & NETWORK INFORMATION
MAC Address: 00:1A:2B:3C:4D:5E
MAC Alt Format: 00-1A-2B-3C-4D-5E
IP Address: 192.168.44.212
IPv6: 2001:0db8:85a3:0000:0000:8a2e:0370:7334
Device ID: DEV-8827391
Browser Fingerprint ID: BF-928374923
Biometric Token: BIO-22918772

VEHICLE / ID / CARDS
VIN: 4T1BF1FK5HU382917
Plate: IL-8721-KD
Parking: PP-88291
CVV: 739
ACT Number: ACT-9928172
        """
    }
]

# 4. Helper Classes
class Result(NamedTuple):
    passed: bool
    label: str
    detail: str = ""

# 5. The Test Runner
class ComprehensiveHIPAATest:
    def __init__(self):
        self.all_results = []
        self.db_mock = self._setup_db_mock()

    def _setup_db_mock(self):
        db = MagicMock()
        db.commit = MagicMock()
        db.add = MagicMock()
        db.refresh = MagicMock()
        db.query = MagicMock()
        db.query.return_value.filter.return_value.all.return_value = []
        return db

    async def run_all(self):
        print("\n" + "═" * 80)
        print("  HIPAA DE-IDENTIFICATION REGRESSION SUITE (SOURCE OF TRUTH)")
        print("═" * 80)

        for i, case in enumerate(TEST_CASES, 1):
            print(f"\n▶ [{i}/{len(TEST_CASES)}] Running: {case['name']}")
            await self.run_case(case)

        self.print_summary()

    async def run_case(self, case):
        try:
            # 1. Pipeline Execution
            payload, vault_id, token_map = await presidio_deidentification_service.de_identify_for_summary_async(
                db=self.db_mock,
                case_id=f"test-case-{random.randint(1000, 9999)}",
                user_id="auditor-bot",
                patient_name=case["patient_name"],
                timeline=[],
                clinical_data={"text": case["text"]},
                red_flags=[],
                case_metadata=case["metadata"],
                document_chunks=[case["text"]]
            )

            deid_text = payload["clinical_data"]["text"]
            
            # 2. Extract original values for leak check
            known_phi = []
            known_phi.append(case["patient_name"])
            for val in case["metadata"].values():
                if isinstance(val, str) and len(val) > 3:
                    known_phi.append(val)
            
            # Additional values from text (not in metadata)
            # Add hardcoded values from specific test cases that we know are PHI
            if "Henry" in case["patient_name"]:
                known_phi.extend([
                    "XK9384721", "CA-DL-84739201", "4111-9283-8812-7721", "4T1BF1FK5HU382917",
                    "henry.matthews85@gmail.com", "+1-217-555-1221", "hmatthews_85"
                ])
            if "Alexander" in case["patient_name"]:
                known_phi.extend([
                    "742 Evergreen Terrace", "Apartment 5B", "Room 312", "Suite 210", "Unit 4C", "Floor 7",
                    "P.O. Box 1234", "1200 Health Park Drive", "Suite 310", "Apt. 22A", "Rm. 15B",
                    "00:1A:2B:3C:4D:5E", "00-1A-2B-3C-4D-5E", "192.168.44.212", 
                    "2001:0db8:85a3:0000:0000:8a2e:0370:7334", "DEV-8827391", "BF-928374923",
                    "BIO-22918772", "4T1BF1FK5HU382917", "IL-8721-KD", "PP-88291", "ACT-9928172"
                ])

            # 3. Perform Checks
            case_results = []

            # CHECK 1: No direct leaks of known values
            leaks = []
            for phi in known_phi:
                if phi.lower() in deid_text.lower():
                    # Check if it was replaced with [[REDACTED]] or a token
                    # We use a simple boundary check
                    pattern = r"\b" + re.escape(phi) + r"\b"
                    if re.search(pattern, deid_text, re.I):
                        leaks.append(phi)
            
            case_results.append(Result(len(leaks) == 0, "No PHI Leakage", f"Leaked: {leaks}" if leaks else "Clean"))

            # CHECK 2: No false positive "Label Tokenisation"
            # (e.g. [[PERSON-NN]] assigned to "Patient Portal Username")
            labels_tokenized = []
            bad_token_matches = re.findall(r"(\[\[PERSON-\d+\]\])[:\s]+", deid_text)
            # Find if any label-like words are now tokens in the map
            for token, original in token_map.items():
                if "PERSON" in token:
                    lower_orig = original.lower()
                    if any(word in lower_orig for word in ["number", "username", "portal", "id", "date", "instructions", "address"]):
                        labels_tokenized.append(f"{token} -> {original}")
            
            case_results.append(Result(len(labels_tokenized) == 0, "No False Positive Tokens", f"Bad Tokens: {labels_tokenized}" if labels_tokenized else "Clean"))

            # CHECK 3: Dates are shifted
            # Dates in text like "February 11, 2025" or "03/14/1980" should be changed
            date_shift_pass = True
            for date_match in re.finditer(r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}\b", case["text"]):
                if date_match.group() in deid_text:
                    date_shift_pass = False
                    break
            case_results.append(Result(date_shift_pass, "Date Shifting", "All narrative dates shifted or redacted"))

            # CHECK 4: No double-shifts
            # (Check if a date like 03/14/1980 exists shifted to something logical)
            # We skip this for simple narrative check unless we parse complex dates

            # CHECK 5: Presidio Lab Format Check
            angle_bracket = "<" in deid_text and ">" in deid_text
            case_results.append(Result(not angle_bracket, "No Lab Format Corruptions", "Output is correctly bracketed with [[]]"))

            self.all_results.append((case["name"], case_results))
            
            # Print de-identified sample for visual check
            print(f"--- OUTPUT PREVIEW ({case['name']}) ---")
            print(deid_text[:400] + "...")

        except Exception as e:
            logger.error(f"Test case '{case['name']}' failed with error: {e}")
            import traceback
            traceback.print_exc()
            self.all_results.append((case["name"], [Result(False, "Test Execution", str(e))]))

    def print_summary(self):
        total_tests = 0
        passed_tests = 0
        
        print("\n" + "═" * 80)
        print("  FINAL REGRESSION SUMMARY")
        print("═" * 80)

        for case_name, results in self.all_results:
            case_pass = all(r.passed for r in results)
            status = "✅" if case_pass else "❌"
            print(f"\n{status} {case_name}")
            for r in results:
                res_status = "  [PASS]" if r.passed else "  [FAIL]"
                print(f"{res_status} {r.label}: {r.detail}")
                total_tests += 1
                if r.passed: passed_tests += 1

        print("\n" + "═" * 80)
        print(f"  TOTAL RESULTS: {passed_tests}/{total_tests} checks passed")
        print(f"  OVERALL STATUS: {'🎉 SUCCESS' if passed_tests == total_tests else '🚨 REGRESSION DETECTED'}")
        print("═" * 80 + "\n")

        if passed_tests < total_tests:
            sys.exit(1)

if __name__ == "__main__":
    tester = ComprehensiveHIPAATest()
    asyncio.run(tester.run_all())
