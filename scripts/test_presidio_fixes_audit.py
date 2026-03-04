#!/usr/bin/env python3
"""
Comprehensive Presidio Fix Verification Test
Tests all 14 fixes outlined in the PRESIDIO_FIX_PLAN.md
"""

import asyncio
import json
import re
import sys
import os
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.presidio_deidentification_service import presidio_deidentification_service

# ═══════════════════════════════════════════════════════════════════════════
# TEST CASES: PACKED WITH SPECIFIC FAILURES REPORTED BY USER
# ═══════════════════════════════════════════════════════════════════════════

TEST_CLINICAL_TEXT = """
ADMISSION RECORD

Patient Name: Henry Jonathan Matthews
Date of Admission: 03/02/2025
Age: 65
Alternative Name (Alias): Johnny Matthews

Patient currently lives at 742 Evergreen Terrace, Apartment 5B, Springfield, IL 62704, United States.
Primary Phone: +1-217-555-8934
Secondary Phone: +1 (217) 555-9382
Email: henry.matthews1985@gmail.com
Portal Username: henrywalker82
Profile Image: henry_matthews_patient_photo_2026.jpg
MAC Address: 00:1B:44:11:3A:B7

Physician Phone: (217) 555-1122
Primary Care Physician: Dr. Michael Smith

CLINICAL NOTES

Henry Jonathan Matthews (DOB: 03/14/1985) presented with shortness of breath.
Patient works at Springfield Nuclear Power Plant as a technician.
Insurance Provider: BlueCross BlueShield of Illinois (Policy: BCBS-IL-449302991)
Employer: Midwest Logistics Corporation
Bank: First National Bank

Patient was seen at Mercy General Hospital for initial triage in Room 402B.
The patient was also evaluated at Henry Ford Hospital for a secondary consult.

VITALS (Ages Stress Test)
Patient 1: 65 years old (Should NOT be redacted)
Patient 2: 92 years old (Should be redacted to 90+)

ENCOUNTER INFORMATION
Medical Encounter Details Hospital
Springfield General Hospital Hospital (Duplication stress test)

IP: 192.168.1.24
Device: PM-DEVICE-778299
"""

CASE_METADATA = {
    "patient_name": "Henry Jonathan Matthews",
    "alias": "Johnny Matthews",
    "employer": "Springfield Nuclear Power Plant",
    "insurance_company": "BlueCross BlueShield of Illinois",
    "facility": "Mercy General Hospital",
}

async def run_audit_test():
    print("\n" + "="*80)
    print("  PRESIDIO FIX AUDIT: VERIFYING 14 PRODUCTION FIXES")
    print("="*80)

    db = MagicMock()
    
    # Run pipeline
    summary = ""
    try:
        payload, vault_id, token_map = await presidio_deidentification_service.de_identify_for_summary_async(
            db=db,
            case_id="audit-test-001",
            user_id="auditor-01",
            patient_name=CASE_METADATA["patient_name"],
            timeline=[],
            clinical_data={"summary": TEST_CLINICAL_TEXT},
            red_flags=[],
            case_metadata=CASE_METADATA,
            score_threshold=0.85
        )
        summary = payload["clinical_data"]["summary"]
    except Exception as e:
        print(f"\n🚨 DE-ID FAILED: {e}")
        # Show what entities were found anyway
        raw_res = presidio_deidentification_service.analyzer.analyze(
            text=TEST_CLINICAL_TEXT, language="en", score_threshold=0.85
        )
        print("\n--- PRESIDIO ENTITIES DETECTED ---")
        for r in raw_res:
             print(f"  {r.entity_type:15} | {r.score:.2f} | '{TEST_CLINICAL_TEXT[r.start:r.end].strip()}'")
        return False

    # Internal scan to show what was found
    if presidio_deidentification_service.analyzer:
        raw_res = presidio_deidentification_service.analyzer.analyze(
            text=TEST_CLINICAL_TEXT, language="en", score_threshold=0.85
        )
        print("\n--- PRESIDIO ENTITIES DETECTED ---")
        for r in raw_res:
            print(f"  {r.entity_type:15} | {r.score:.2f} | '{TEST_CLINICAL_TEXT[r.start:r.end].strip()}'")
    
    print("\n--- DE-IDENTIFIED OUTPUT SAMPLE ---")
    print(summary)
    print("-" * 40)

    checks = []

    # 1. Phone +1 prefix
    checks.append(("Phone +1- format", "+1-217-555-8934" not in summary))
    checks.append(("Phone +1 ( format", "+1 (217) 555-9382" not in summary))
    
    # 2. City/State/Country
    checks.append(("City (Springfield)", "Springfield" not in summary))
    checks.append(("Country (United States)", "United States" not in summary))
    checks.append(("Country (USA/U.S.)", "USA" not in summary and "U.S." not in summary))
    checks.append(("City/State Pair (Springfield, IL)", "Springfield, IL" not in summary))

    # 3. MAC Address
    checks.append(("MAC Address", "00:1B:44:11:3A:B7" not in summary))

    # 4. Employer/Insurer (from metadata)
    checks.append(("Employer (Power Plant)", "Springfield Nuclear Power Plant" not in summary))
    checks.append(("Insurer (BlueCross)", "BlueCross BlueShield of Illinois" not in summary))

    # 5. Sub-address
    checks.append(("Apartment 5B", "Apartment 5B" not in summary))
    checks.append(("Room 402B", "Room 402B" not in summary))

    # 6. Over-Redaction: Single Name in Hospital name
    checks.append(("No over-redaction of 'Henry' in Hospital Name", "[[PERSON-01]] Ford Hospital" not in summary))

    # 7. Over-Redaction: Usernames/Filenames
    checks.append(("Username kept", "henrywalker82" in summary))
    checks.append(("Filename kept", "henry_matthews_patient_photo_2026.jpg" in summary))

    # 8. Over-Redaction: Header Labels
    checks.append(("Header label 'Physician Phone' preserved", "Physician Phone" in summary))
    checks.append(("Header label 'Encounter Details' preserved", "Encounter Details" in summary))

    # 9. Hospital Duplication
    checks.append(("No 'Hospital Hospital' duplication", "Hospital Hospital" not in summary))

    # 10. Age Handling
    checks.append(("Age 65 kept", "65 years old" in summary or "65 year old" in summary))
    checks.append(("Age 92 redacted to 90+", "90+" in summary))
    checks.append(("Age 92 original 92 gone", " 92 " not in summary))

    print("\n--- RESULTS ---")
    all_passed = True
    for label, passed in checks:
        status = "✅ PASS" if passed else "❌ FAIL"
        if not passed: all_passed = False
        print(f"  {status:7} | {label}")

    print("\n" + "="*80)
    if all_passed:
        print("  🎉 ALL AUDIT CHECKS PASSED")
    else:
        print("  🚨 SOME CHECKS FAILED")
    print("="*80 + "\n")
    
    return all_passed

if __name__ == "__main__":
    asyncio.run(run_audit_test())
