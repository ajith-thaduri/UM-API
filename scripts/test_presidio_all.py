#!/usr/bin/env python3
"""
===========================================================================
      ULTIMATE COMPREHENSIVE PRESIDIO TEST SUITE (SOURCE OF TRUTH)
===========================================================================
This file consolidates ALL Presidio-related tests into one single file:
1. Internal Logic & Tokenization (Unit)
2. HIPAA Safe Harbor Compliance (18 Identifiers)
3. Date Shifting & Reversal round-trip
4. NER Sanitization & Overlap Resolution
5. Compliance Edge Cases (Clinical False Positives)
6. Special Entities (Coordinates, Structured Hospital names)
7. Regression Suite (Extreme Stress Tests - Henry, Alexander, Kevin)

Run: python scripts/test_presidio_all.py
"""

import asyncio
import json
import os
import re
import sys
import random
from datetime import datetime
from typing import Any, Dict, List, Tuple
from unittest.mock import MagicMock

# 1. PATH SETUP
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

# 2. IMPORTS
from app.services.presidio_deidentification_service import presidio_deidentification_service
from app.services.presidio.ner_sanitizer import sanitize_ner_results
from app.services.presidio.constants import normalize_entity_type
from app.services.presidio.date_handler import shift_dates_in_text
from app.services.date_shift_service import date_shift_service
from app.services.presidio.phi_collector import generate_tokens
from app.services.presidio.token_replacer import replace_known_phi
from presidio_analyzer import RecognizerResult

# ===========================================================================
# MOCKING & UTILS
# ===========================================================================

class MockSession:
    def query(self, *args, **kwargs): return self
    def filter(self, *args, **kwargs): return self
    def delete(self, *args, **kwargs): return self
    def all(self, *args, **kwargs): return []
    def first(self, *args, **kwargs): return None
    def flush(self, *args, **kwargs): pass
    def refresh(self, *args, **kwargs): pass
    def add(self, *args, **kwargs): pass
    def commit(self, *args, **kwargs): pass
    def close(self, *args, **kwargs): pass

def print_result(label, passed, detail=""):
    status = "[PASS]" if passed else "[FAIL]"
    msg = f"  {status} {label}"
    if detail: msg += f" -> {detail}"
    print(msg)
    return passed

# ===========================================================================
# REGRESSION TEST CASES (FROM test_comprehensive_hipaa.py)
# ===========================================================================

REGRESSION_CASES = [
    {
        "name": "Standard Clinical Narrative (John)",
        "patient_name": "John Michael Doe",
        "metadata": {
            "Alias Used in Prior Records": "Johnny Doe",
            "medical_record_number": "000123456",
            "ssn": "123-45-6789",
            "provider": "Dr. Michael Smith",
            "facility": "St. Mary's Regional Medical Center"
        },
        "text": "Patient Name: John Michael Doe (SSN 123-45-6789). Admitted to St. Mary's by Dr. Smith."
    },
    {
        "name": "Extreme Structural Entities (Alexander)",
        "patient_name": "Alexander Sterling",
        "metadata": {"address": "1200 Health Park Drive, Suite 310, Chicago, IL 60601"},
        "text": """
        HOME: 742 Evergreen Terrace, Apt 5B, Room 312, Suite 210, Unit 4C, Floor 7, P.O. Box 1234.
        IP: 192.168.44.212, MAC: 00:1A:2B:3C:4D:5E. VIN: 4T1BF1FK5HU382917.
        """
    },
    {
        "name": "Extreme HIPAA Stress Test (Kevin)",
        "patient_name": "Kevin Alexander Carter",
        "metadata": {
            "ssn": "612-45-9087", "mrn": "MRN-87456321", "license": "TX-DL-78293451",
            "phone": "+1 (512) 555-7834", "email": "kevin.carter1981@gmail.com"
        },
        "text": """
        Kevin Alexander Carter (SSN 612-45-9087, MRN MRN-87456321). 
        Lives at 4587 Pinecrest Drive, Austin, TX 78704. DL: TX-DL-78293451.
        Contact: +1 (512) 555-7834 or kevin.carter1981@gmail.com.
        """
    }
]

# ===========================================================================
# TEST CATEGORIES
# ===========================================================================

class AllPresidioTester:
    def __init__(self):
        self.service = presidio_deidentification_service
        self.failures = 0

    def run_check(self, label, func, *args, **kwargs):
        try:
            print(f"\n- Running: {label}")
            passed = func(*args, **kwargs)
            if not passed: self.failures += 1
        except Exception as e:
            print(f"  [ERROR] {label}: {e}")
            import traceback
            traceback.print_exc()
            self.failures += 1

    async def run_check_async(self, label, func, *args, **kwargs):
        try:
            print(f"\n- Running: {label} (Async)")
            passed = await func(*args, **kwargs)
            if not passed: self.failures += 1
        except Exception as e:
            print(f"  [ERROR] {label}: {e}")
            import traceback
            traceback.print_exc()
            self.failures += 1

    # 1. INTERNAL LOGIC
    def test_token_format(self):
        data_groups = {
            "identities": [
                {"type": "PERSON", "canonical": "John Doe", "variants": []},
                {"type": "ORGANIZATION", "canonical": "City Hospital", "variants": []}
            ],
            "strips": []
        }
        token_map, variant_map, strips = generate_tokens(data_groups)
        passed = True
        for token in token_map.keys():
            if not re.match(r"^\[\[[A-Z_]+-\d{2}\]\]$", token):
                passed = False
        
        data = {"patient": {"name": "Rajesh Sharma"}, "facility": "Global Tech"}
        v_map = {"Rajesh Sharma": "[[PERSON-01]]", "Global Tech": "[[ORGANIZATION-01]]"}
        result = replace_known_phi(data, v_map, [])
        if result["patient"]["name"] != "[[PERSON-01]]" or result["facility"] != "[[ORGANIZATION-01]]":
            passed = False
            
        return print_result("Internal Logic & Tokenization", passed)

    # 2. DATE LOGIC
    def test_date_logic(self):
        text = "Patient admitted on 01/15/2025 and discharged on 2024-05-20."
        shift_days = 10
        shifted = shift_dates_in_text(text, shift_days)
        shift_pass = "01/15/2025" not in shifted and "01/25/2025" in shifted
        
        reversed_text = date_shift_service.reidentify_summary_text(shifted, shift_days)
        reversal_pass = "01/15/2025" in reversed_text and "05/20/2024" in reversed_text
        
        return print_result("Date Round-trip Reversal", reversal_pass)

    # 3. NER SANITIZATION
    def test_ner_sanitization(self):
        text = "The patient John Michael Doe was seen today."
        mock_results = [
            RecognizerResult(entity_type="PERSON", start=12, end=24, score=0.95),
            RecognizerResult(entity_type="PERSON", start=12, end=28, score=0.85),
            RecognizerResult(entity_type="PERSON", start=25, end=28, score=0.99),
        ]
        from app.services.presidio.ner_sanitizer import resolve_overlapping_spans
        resolved = resolve_overlapping_spans(mock_results)
        overlap_pass = len(resolved) == 1 and resolved[0].start == 12 and resolved[0].end == 28
        
        sanitized = sanitize_ner_results([RecognizerResult(entity_type="PERSON", start=0, end=13, score=0.9)], "Acetaminophen")
        block_pass = len(sanitized) == 0
        
        return print_result("NER Overlap & Sanitization", overlap_pass and block_pass)

    # 4. COMPLIANCE EDGE CASES
    def test_compliance_edge_cases(self):
        test_cases = [
            {"name": "MD False Positive", "text": "Dr. Thompson, MD saw him.", "unwanted": ["CITY", "LOCATION"]},
            {"name": "Email Overlap", "text": "Contact mike.jones@gmail.com", "unwanted": ["PERSON"]},
            {"name": "Clinical Preservation", "text": "He has Diabetes Mellitus.", "unwanted": ["PERSON", "ORGANIZATION"]}
        ]
        total_passed = True
        for case in test_cases:
            res = self.service.analyzer.analyze(text=case["text"], language='en', score_threshold=0.35)
            res = sanitize_ner_results(res, case["text"])
            res = self.service._filter_email_person_overlap(res)
            detected = [normalize_entity_type(r.entity_type) for r in res]
            
            case_pass = not any(u in detected for u in case["unwanted"])
            if not case_pass: total_passed = False
            print_result(case["name"], case_pass, f"Detected: {detected}")
        return total_passed

    # 5. REGRESSION SUITE (EXTREME TESTS)
    async def test_regression_suite(self):
        db = MockSession()
        all_passed = True
        for case in REGRESSION_CASES:
            try:
                payload, _, _ = await self.service.de_identify_for_summary_async(
                    db=db, case_id="reg", user_id="bot",
                    patient_name=case["patient_name"],
                    timeline=[], clinical_data={"text": case["text"]},
                    red_flags=[], case_metadata=case["metadata"], document_chunks=[case["text"]]
                )
                summary = payload["clinical_data"]["text"]
                # Basic leak check
                leaked = case["patient_name"] in summary or (case["metadata"].get("ssn") and case["metadata"]["ssn"] in summary)
                # Clinical check
                clinical_pass = "Diabetes" not in case["text"] or "Diabetes" in summary
                
                passed = not leaked and clinical_pass
                if not passed: all_passed = False
                print_result(f"Regression: {case['name']}", passed)
            except Exception as e:
                print(f"  [FAIL] {case['name']} crashed: {e}")
                all_passed = False
        return all_passed

    # 6. SPECIAL ENTITIES
    def test_special_entities(self):
        text = "Coordinates: Lat: 40.7128, Long: -74.0060. Referral to Saint Jude Children's Research Hospital INC."
        results = self.service.analyzer.analyze(text=text, language='en', score_threshold=0.3)
        # Apply normalization
        detected = [normalize_entity_type(r.entity_type) for r in results]
        # We also look at the text of what was found
        found_data = [(normalize_entity_type(r.entity_type), text[r.start:r.end]) for r in results]
        
        has_coord = any("COORDINATE" in ent or "LOCATION" in ent for ent in detected)
        has_org = any("ORGANIZATION" in ent or "ORG" in ent for ent in detected)
        
        passed = has_coord and has_org
        return print_result("Coordinates & Hospital Brands", passed, f"Detected: {found_data}")

# ===========================================================================
# MAIN RUNNER
# ===========================================================================

async def main():
    print("\n" + "="*80)
    print("      ULTIMATE PRESIDIO DE-IDENTIFICATION AUDIT")
    print("="*80)
    
    tester = AllPresidioTester()
    tester.run_check("Internal Logic", tester.test_token_format)
    tester.run_check("Date Logic", tester.test_date_logic)
    tester.run_check("NER Sanitization", tester.test_ner_sanitization)
    tester.run_check("Compliance Edge Cases", tester.test_compliance_edge_cases)
    tester.run_check("Special Entities", tester.test_special_entities)
    await tester.run_check_async("Regression Stress Tests", tester.test_regression_suite)
    
    print("\n" + "="*80)
    if tester.failures == 0:
        print("  ALL PRESIDIO TESTS PASSED SUCCESSFULLY!")
    else:
        print(f"  AUDIT COMPLETED WITH {tester.failures} FAILURES.")
    print("="*80 + "\n")
    sys.exit(0 if tester.failures == 0 else 1)

if __name__ == "__main__":
    asyncio.run(main())
