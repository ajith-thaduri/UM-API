
import asyncio
from typing import Dict, Any, List
from app.services.presidio_deidentification_service import presidio_deidentification_service

async def test_overlap_resolution():
    """
    Test that 'John Michael Doe' beats 'John Michael' and 'Michael Doe'.
    """
    print("\n--- TESTING OVERLAP RESOLUTION ---")
    
    text = "The patient John Michael Doe was seen today by Dr. Smith."
    
    # We simulate what the analyzer would return
    from presidio_analyzer import RecognizerResult
    
    # Simulate overlapping results
    mock_results = [
        RecognizerResult(entity_type="PATIENT_NAME", start=12, end=24, score=0.95),  # John Michael
        RecognizerResult(entity_type="PERSON", start=12, end=28, score=0.85),        # John Michael Doe
        RecognizerResult(entity_type="LAST_NAME", start=25, end=28, score=0.99),     # Doe
    ]
    
    print(f"Original Text: {text}")
    print("Mock Detection Results:")
    for r in mock_results:
        print(f" - {r.entity_type} [{r.start}:{r.end}] '{text[r.start:r.end]}' score={r.score}")
    
    token_map = {}
    
    # Call the residual PHI processing logic which now uses _resolve_overlapping_spans
    de_id_text = presidio_deidentification_service._process_residual_phi_in_string(
        text, mock_results, token_map, score_threshold=0.35
    )
    
    print(f"\nDe-identified Text: {de_id_text}")
    print(f"Token Map: {token_map}")
    
    # Verification
    # Expected: Only 'John Michael Doe' is tokenized
    if "[[PERSON-01]]" in de_id_text and "John Michael Doe" in token_map.values():
        if "John Michael" not in token_map.values() and "Doe" not in token_map.values():
            print("\n✅ SUCCESS: Longest span 'John Michael Doe' correctly resolved and replaced.")
        else:
            print("\n❌ FAILURE: Redundant tokens found in map.")
    else:
        print("\n❌ FAILURE: Longest span not tokenized correctly.")

if __name__ == "__main__":
    asyncio.run(test_overlap_resolution())
