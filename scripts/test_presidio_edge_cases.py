#!/usr/bin/env python3
"""
Stress Test and Edge Case Detection for Presidio De-identification
Focuses on clinical eponyms, ambiguous locations, and rare PHI categories.
"""

import asyncio
import os
import sys
import re
from unittest.mock import MagicMock

# Add project root to sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.presidio_deidentification_service import presidio_deidentification_service
from app.core.config import settings

# ═══════════════════════════════════════════════════════════════════════════
# EDGE CASE SCENARIOS
# ═══════════════════════════════════════════════════════════════════════════

TEST_SCENARIOS = {
    "1_CLINICAL_EPONYMS": {
        "text": "The patient has Parkinson's disease and was evaluated for Crohn's flare. We used the Glasgow Coma Scale. Also noted Raynaud's phenomenon.",
        "expect_kept": ["Parkinson's", "Crohn's", "Glasgow Coma Scale", "Raynaud's"],
        "expect_redacted": []
    },
    "2_AMBIGUOUS_LOCATIONS": {
        "text": "The patient is from Reading, Pennsylvania. We checked his mobile phone. He visited Buffalo for a consult. He works in Washington state.",
        "expect_kept": ["mobile phone"],
        "expect_redacted": ["Reading", "Pennsylvania", "Buffalo", "Washington"]
    },
    "3_PROFESSIONAL_CREDENTIALS": {
        "text": "Attending: Jane Doe, MD, FACS. Resident: Bob Smith, PGY-3. Nurse: Alice Jones, RN. Social Worker: Mike Brown, LCSW.",
        "expect_kept": ["MD", "FACS", "PGY-3", "RN", "LCSW", "Attending", "Resident", "Nurse"],
        "expect_redacted": ["Jane Doe", "Bob Smith", "Alice Jones", "Mike Brown"]
    },
    "4_DEVICE_SERIALS": {
        "text": "Pacemaker Model: Medtronic Azure S. Serial Number: SN-48829-X12. Implanted on 05/12/2021 by Dr. Miller.",
        "expect_kept": ["Medtronic Azure S"],
        "expect_redacted": ["SN-48829-X12", "Miller"]
    },
    "5_JSON_ESCAPES": {
        "text": "Entry: {\"note\": \"Patient John Doe seen.\\nFollow-up in Chicago, IL.\\nStatus: Stable.\"}",
        "expect_kept": ["note", "Status", "Stable"],
        "expect_redacted": ["John Doe", "Chicago", "IL"]
    },
    "6_PARTIAL_IDENTITIES": {
        "text": "The patient J. Smith remains inpatient. Mrs. Johnson was notified of the status. Pt. John Q. Smith-Matthews attended.",
        "expect_kept": ["Pt.", "Mrs.", "inpatient"],
        "expect_redacted": ["J. Smith", "Johnson", "John Q. Smith-Matthews"]
    },
    "7_SENSITIVE_PHRASES": {
        "text": "Patient resides at the homeless shelter on 5th Street. Employer: Self-Employed. Insurance: Medicare Part B.",
        "expect_kept": ["Medicare Part B", "Self-Employed"],
        "expect_redacted": ["homeless shelter", "5th Street"]
    }
}

CASE_METADATA = {
    "patient_name": "John Q. Smith-Matthews",
    "facility": "General Hospital",
}

async def run_edge_case_audit():
    print("\n" + "="*80)
    print("  PRESIDIO STRESS TEST: DETECTING REMAINING ISSUES")
    print("="*80)

    db = MagicMock()
    
    total_checks = 0
    passed_checks = 0
    issues_found = []

    for scenario_name, data in TEST_SCENARIOS.items():
        print(f"\n▶ Scenario: {scenario_name}")
        text = data["text"]
        
        try:
            payload, vault_id, token_map = await presidio_deidentification_service.de_identify_for_summary_async(
                db=db,
                case_id=f"test-{scenario_name}",
                user_id="tester",
                patient_name=CASE_METADATA["patient_name"],
                timeline=[],
                clinical_data={"summary": text},
                red_flags=[],
                case_metadata=CASE_METADATA,
                score_threshold=0.85
            )
            de_id_text = payload["clinical_data"]["summary"]
        except Exception as e:
            print(f"  ❌ PIPELINE FAILED: {e}")
            issues_found.append(f"{scenario_name}: Pipeline Error ({e})")
            continue

        print(f"  Original: {text}")
        print(f"  De-ID:    {de_id_text}")

        # Check Expectations
        for word in data["expect_kept"]:
            total_checks += 1
            if word in de_id_text:
                passed_checks += 1
            else:
                print(f"  ❌ OVER-REDACTED: '{word}' missing")
                issues_found.append(f"{scenario_name}: Over-redacted '{word}'")

        for word in data["expect_redacted"]:
            total_checks += 1
            if word not in de_id_text:
                passed_checks += 1
            else:
                print(f"  ❌ LEAKED: '{word}' still present")
                issues_found.append(f"{scenario_name}: Leaked '{word}'")

    print("\n" + "="*80)
    print(f"  SUMMARY: {passed_checks}/{total_checks} Checks Passed")
    print("="*80)

    if issues_found:
        print("\n🚨 ISSUES IDENTIFIED:")
        for issue in issues_found:
            print(f"  - {issue}")
    else:
        print("\n✨ NO ISSUES FOUND IN EDGE CASES")
    print("="*80 + "\n")

    # Final Internal Scan for debugging
    if presidio_deidentification_service.analyzer:
        print("--- INTERNAL ANALYZER SCAN (THRESHOLD 0.85) ---")
        full_text = "\n".join([d["text"] for d in TEST_SCENARIOS.values()])
        results = presidio_deidentification_service.analyzer.analyze(
            text=full_text, language="en", score_threshold=0.85
        )
        for r in results:
            span = full_text[r.start:r.end].strip()
            print(f"  {r.entity_type:15} | {r.score:.2f} | '{span}'")

if __name__ == "__main__":
    asyncio.run(run_edge_case_audit())
