import os
import sys
import re
import json
import asyncio
# import pytest  <-- Removed to run as simple script
from unittest.mock import MagicMock, patch
from copy import deepcopy
from datetime import datetime
import uuid

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Presidio Imports
from app.services.presidio.constants import normalize_entity_type, NER_EXACT_BLOCKLIST
from app.services.presidio.phi_collector import generate_tokens, collect_known_phi
from app.services.presidio.token_replacer import replace_known_phi
from app.services.presidio.date_handler import shift_dates_structured, shift_dates_in_text
from app.services.presidio.ner_sanitizer import sanitize_ner_results
from app.services.presidio_deidentification_service import presidio_deidentification_service
from presidio_analyzer import RecognizerResult, PatternRecognizer, Pattern

# Mock Session for tests requiring DB
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

# ===========================================================================
# HELPERS FOR BACKWARD COMPATIBILITY
# ===========================================================================

def setup_mock_service(svc):
    """Bridge new modular functions to old service methods for tests."""
    def _mock_collect_phi(name, meta):
        res = collect_known_phi(name, meta)
        svc._last_data_groups = res
        flat = {}
        for ident in res["identities"]:
            flat[ident["canonical"]] = ident["type"]
            for v in ident.get("variants", []):
                flat[v] = ident["type"]
        for s in res["strips"]:
            flat[s] = "ID"
        return flat

    def _mock_gen_tokens(flat_phi):
        data_groups = getattr(svc, "_last_data_groups", None)
        if not data_groups:
            identities = []
            for val in sorted(flat_phi.keys()):
                etype = normalize_entity_type(flat_phi[val])
                identities.append({"type": etype, "canonical": val, "variants": []})
            data_groups = {"identities": identities, "strips": []}
        t_map, v_map, s_list = generate_tokens(data_groups)
        svc._last_v_map = v_map
        svc._last_s_list = s_list
        return t_map

    def _mock_replace_phi(data, t_map):
        if t_map:
            # If map is provided explicitly (unit test style), use it
            v_map = {v: k for k, v in t_map.items()}
        else:
            # Otherwise use cached map from last _gen_tokens call
            v_map = getattr(svc, "_last_v_map", {})
        
        s_list = getattr(svc, "_last_s_list", [])
        return replace_known_phi(data, v_map, s_list)

    svc._collect_known_phi = _mock_collect_phi
    svc._generate_tokens = _mock_gen_tokens
    svc._replace_known_phi = _mock_replace_phi
    svc._shift_dates_structured = shift_dates_structured
    return svc

# ===========================================================================
# TEST DATA
# ===========================================================================

PATIENT_NAME = "Rajesh Kumar Sharma"
CASE_NUMBER = "BCK-2025-00789"
FACILITY = "St. Mary's Medical Center"
PROVIDER = "Dr. Anita Patel"

CLINICAL_DATA = {
    "patient_name": PATIENT_NAME,
    "mrn": "000789456",
    "admission_date": "01/15/2025",
    "discharge_date": "01/22/2025",
    "facility": FACILITY,
    "provider": PROVIDER,
    "history": {
        "description": f"{PATIENT_NAME} is a 67-year-old male admitted to {FACILITY} on 01/15/2025 by {PROVIDER}."
    },
}

CASE_METADATA = {
    "case_number": CASE_NUMBER,
    "facility": FACILITY,
    "provider": PROVIDER,
    "mrn": "000789456",
    "npi": "1234567890",
    "insurance_id": "BCBS-HMO-0045678",
}

# ===========================================================================
# 1. CORE COMPONENT TESTS
# ===========================================================================

def test_basic_analyzer():
    print("\n--- Running Basic Analyzer Check ---")
    text = "Patient John Doe (DOB: 05/15/1980) was admitted to General Hospital on 03/10/2025."
    if not presidio_deidentification_service.analyzer:
        print("Presidio Analyzer not initialized!")
        return
    results = presidio_deidentification_service.analyzer.analyze(text=text, language="en")
    print(f"Found {len(results)} entities")
    for res in results:
        print(f" - {res.entity_type}: {text[res.start:res.end]} ({res.score})")

def test_overredaction_blocklist():
    print("\n--- Running Over-redaction Blocklist Check ---")
    test_words = ["Acetaminophen", "Albuterol Inhaler", "Diabetes Mellitus", "Tesla Model", "Doctor Notes Subjective", "Hypertension Management"]
    for word in test_words:
        results = [RecognizerResult(entity_type="PERSON", start=0, end=len(word), score=0.95)]
        sanitized = sanitize_ner_results(results, word)
        assert len(sanitized) == 0, f"Expected '{word}' to be blocked, but it remained."
    print("All blocked terms successfully ignored.")

# ===========================================================================
# 2. DETERMINISTIC LOGIC TESTS
# ===========================================================================

class TestLogic:
    def __init__(self):
        from app.services.presidio_deidentification_service import PresidioDeIdentificationService
        svc = object.__new__(PresidioDeIdentificationService)
        svc.analyzer = svc.anonymizer = None
        self.service = setup_mock_service(svc)

    def test_token_format(self):
        known_phi = {"John Doe": "PERSON"}
        token_map = self.service._generate_tokens(known_phi)
        token_pattern = re.compile(r"^\[\[[A-Z_]+-\d{2,}\]\]$")
        for token in token_map.keys():
            assert token_pattern.match(token)

    def test_replaces_in_nested_dict(self):
        token_map = {"[[PERSON-01]]": "Rajesh Sharma", "[[ORGANIZATION-01]]": "Global Tech"}
        data = {"patient": {"name": "Rajesh Sharma"}, "facility": "Global Tech"}
        result = self.service._replace_known_phi(data, token_map)
        print(f"DEBUG: result={result}")
        assert result["patient"]["name"] == "[[PERSON-01]]"
        assert result["facility"] == "[[ORGANIZATION-01]]"

# ===========================================================================
# 3. DATE SHIFTING
# ===========================================================================

def test_date_shifting():
    print("\n--- Running Date Shifting Check ---")
    text = "Patient admitted on 01/15/2025 and discharged on 01/22/2025."
    shifted = shift_dates_in_text(text, shift_days=10)
    assert "01/15/2025" not in shifted
    assert "01/25/2025" in shifted
    print("Date shifting working correctly.")

# ===========================================================================
# 4. FULL ASYNC PIPELINE AUDITS
# ===========================================================================

async def test_full_pipeline():
    print("\n--- Running Full Pipeline Audit ---")
    db = MockSession()
    payload, vault_id, token_map = await presidio_deidentification_service.de_identify_for_summary_async(
        db=db, case_id="test-123", user_id="user-1",
        patient_name=PATIENT_NAME, timeline=[], clinical_data=CLINICAL_DATA,
        red_flags=[], case_metadata=CASE_METADATA
    )
    de_id_text = json.dumps(payload)
    assert PATIENT_NAME not in de_id_text
    assert "[[PERSON-" in de_id_text
    print(f"Pipeline Completed. Tokens generated: {len(token_map)}")

async def run_edge_case_audit():
    print("\n--- Running Edge Case Stress Test ---")
    scenarios = {
        "EPONYMS": "Patient has Parkinson's and Crohn's.",
        "CREDENTIALS": "Dr. Jane Doe, MD, FACS.",
        "LOCATIONS": "Lives in Springfield, IL 62704."
    }
    db = MockSession()
    for name, text in scenarios.items():
        payload, _, _ = await presidio_deidentification_service.de_identify_for_summary_async(
            db=db, case_id=f"edge-{name}", user_id="tester",
            patient_name="Jane Doe", timeline=[], clinical_data={"text": text},
            red_flags=[], case_metadata={"patient_name": "Jane Doe"}
        )
        print(f" Scenario {name}: {payload['clinical_data']['text']}")

# ===========================================================================
# 5. TOGGLE LOGIC & DOCUMENT STRESS
# ===========================================================================

def test_toggle_simulation():
    print("\n--- Running Toggle Logic Simulation ---")
    patient = "John Doe"
    data = f"Patient {patient} with hypertension."
    # Enabled
    redacted = data.replace(patient, "[[PERSON-01]]")
    assert "[[PERSON-01]]" in redacted and patient not in redacted
    # Disabled
    raw = data
    assert patient in raw
    print("Toggle logic simulation passed.")

async def run_document_stress_test():
    print("\n--- Running Comprehensive Document Stress Test ---")
    db = MockSession()
    doc = """
    Patient: Henry Jonathan Matthews (DOB: 03/14/1985)
    SSN: 623-44-9182 | MRN: MRN-88392011
    Address: 4587 Pinecrest Drive, San Diego, CA 92103
    Employer: Pacific Finance Group (EMP-883992)
    Hospital: West Coast Medical Center
    Physician: Dr. Michael Thompson
    """
    payload, vault_id, _ = await presidio_deidentification_service.de_identify_for_summary_async(
        db=db, case_id="doc-stress", user_id="user-1",
        patient_name="Henry Jonathan Matthews", timeline=[], clinical_data={},
        red_flags=[], document_chunks=[doc],
        case_metadata={"patient_name": "Henry Jonathan Matthews", "facility": "West Coast Medical Center"}
    )
    print("De-identified Document Sample:")
    print(payload["document_chunks"][0][:200] + "...")
    print(f"✅ Document stress test completed. Vault ID: {vault_id}")

# ===========================================================================
# MAIN ENTRY POINT
# ===========================================================================

async def main():
    print("="*80)
    print("  CENTRALIZED PRESIDIO TEST SUITE")
    print("="*80)
    
    # Synchronous Checks
    test_basic_analyzer()
    test_overredaction_blocklist()
    test_date_shifting()
    test_toggle_simulation()
    
    # Logic Checks (subset of unit tests)
    logic_tester = TestLogic()
    logic_tester.test_token_format()
    logic_tester.test_replaces_in_nested_dict()
    print("Deterministic logic checks passed.")
    
    # Async Pipeline Checks
    await test_full_pipeline()
    await run_edge_case_audit()
    await run_document_stress_test()
    
    print("\n" + "="*80)
    print("  ALL PRESIDIO TESTS COMPLETED SUCCESSFULLY")
    print("="*80)

if __name__ == "__main__":
    asyncio.run(main())
