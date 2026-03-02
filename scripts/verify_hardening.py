import asyncio
import sys
import re
from presidio_analyzer import RecognizerResult

sys.path.append("/Users/ajiththaduri/Desktop/V2/UM-API")
from app.services.presidio_deidentification_service import presidio_deidentification_service

async def test_lab_logic():
    print("--- TESTING LAB ENDPOINT HARDENING ---")
    text = "The patient John Michael Doe was seen by Dr. Smith."
    
    # Simulate Presidio analysis results with overlaps (what caused the corruption)
    mock_results = [
        RecognizerResult(entity_type="PATIENT_FULL_NAME", start=12, end=28, score=0.95), # John Michael Doe
        RecognizerResult(entity_type="PERSON", start=12, end=24, score=0.85),            # John Michael
    ]
    
    # Step 1: Resolve overlaps (Longest wins)
    resolved = presidio_deidentification_service._resolve_overlapping_spans(mock_results)
    print(f"Resolved spans count: {len(resolved)}")
    for r in resolved:
        print(f" - {r.entity_type} [{r.start}:{r.end}] '{text[r.start:r.end]}'")
    
    if len(resolved) == 1 and resolved[0].entity_type == "PATIENT_FULL_NAME":
        print("✅ SUCCESS: Overlap resolved correctly.")
    else:
        print("❌ FAILED: Overlap resolution failed.")

    print("\n--- TESTING STREET ADDRESS HARDENING ---")
    false_street = "03/02/2025 under the care of Dr"
    res_false = RecognizerResult(entity_type="STREET_ADDRESS", start=0, end=len(false_street), score=0.9)
    sanitized_false = presidio_deidentification_service._sanitize_ner_results([res_false], false_street)
    print(f"Sanitized results for false street: {len(sanitized_false)}")
    if len(sanitized_false) == 0:
        print("✅ SUCCESS: False street address rejected.")
    else:
        print("❌ FAILED: False street address accepted.")

    true_street = "123 Main Street"
    res_true = RecognizerResult(entity_type="STREET_ADDRESS", start=0, end=len(true_street), score=0.9)
    sanitized_true = presidio_deidentification_service._sanitize_ner_results([res_true], true_street)
    print(f"Sanitized results for true street: {len(sanitized_true)}")
    if len(sanitized_true) == 1:
        print("✅ SUCCESS: Valid street address accepted.")
    else:
        print("❌ FAILED: Valid street address rejected.")

    print("\n--- TESTING SAFE HARBOR RECOGNIZERS ---")
    pii_text = "IP: 192.168.1.45, Plate: IL-ABC-7890, Passport: X12345678, License: D1234567, SSN: 123-45-6789"
    
    # Initialize analyzer if needed (but we already did it in the service init)
    results = presidio_deidentification_service.analyzer.analyze(
        text=pii_text,
        language="en",
        score_threshold=0.4
    )
    
    types_found = {r.entity_type for r in results}
    print(f"Types found: {types_found}")
    
    expected = {"IP_ADDRESS", "VEHICLE_PLATE", "PASSPORT", "DRIVERS_LICENSE", "SSN"}
    missing = expected - types_found
    if not missing:
        print("✅ SUCCESS: All Safe Harbor identifiers detected.")
    else:
        print(f"❌ FAILED: Missing detectors for: {missing}")

if __name__ == "__main__":
    asyncio.run(test_lab_logic())
