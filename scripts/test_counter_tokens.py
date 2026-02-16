
import sys
import os
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from app.services.presidio_deidentification_service import presidio_deidentification_service

def test_counter_tokens():
    print("=== Testing Counter-Based Token Generation ===\n")
    
    # 1. Test Deterministic Generation (Known PHI)
    print("Test 1: Deterministic Known PHI")
    known_phi = {
        "John Doe": "PERSON",
        "Jane Smith": "PERSON", 
        "Mayo Clinic": "HOSPITAL"
    }
    
    token_map = presidio_deidentification_service._generate_tokens(known_phi)
    print(f"Token Map: {token_map}")
    
    # Check for correct format
    if "[[PERSON-01]]" in token_map and "[[PERSON-02]]" in token_map:
        print("  ✅ PERSON counters incremented correctly")
    else:
        print("  ❌ Failed to increment PERSON counters")
        sys.exit(1)
        
    if "[[HOSPITAL-01]]" in token_map:
        print("  ✅ HOSPITAL counter started correctly")
    else:
        print("  ❌ Failed to start HOSPITAL counter")
        sys.exit(1)

    # 2. Test Presidio Scan (Free Text)
    print("\nTest 2: Presidio Scan (Dynamic Counters)")
    text = "Dr. Alice Wonderland met with patient Bob Builder at 742 Evergreen Terrace."
    
    # Mock token map with some existing tokens to test continuation
    token_map = {
        "[[PERSON-01]]": "John Doe"
    }
    
    processed_text = text
    # We need to simulate the service flow where text is processed 
    # and new tokens are added to the map
    
    # The service method _process_single_string updates token_map in place
    dummy_obj = {"text": text}
    presidio_deidentification_service._process_single_string(dummy_obj, "text", text, token_map, score_threshold=0.40)
    
    result_text = dummy_obj["text"]
    print(f"Original: {text}")
    print(f"Redacted: {result_text}")
    print(f"Token Map: {token_map}")
    
    # Check if new tokens are generated with correct types
    # "Dr. Alice Wonderland" -> PROVIDER
    # "Bob Builder" -> PATIENT_FULL_NAME (labels) or PERSON
    
    # We expect distinct counters for distinct types:
    # PERSON-01 (John Doe)
    # PROVIDER-01 (Dr. Alice)
    # PATIENT_FULL_NAME-01 (Bob Builder) OR PERSON-02 if detected as PERSON
    
    print(f"  Token Map Keys: {list(token_map.keys())}")
    
    if "[[PROVIDER-01]]" in result_text:
         print("  ✅ PROVIDER counter started at 01 correctly")
    else:
         print(f"  ❌ Failed to detect/tokenise PROVIDER. Result: {result_text}")
         sys.exit(1)

    if "[[PATIENT_FULL_NAME-01]]" in result_text or "[[PERSON-02]]" in result_text:
         print("  ✅ Patient detected with correct counter")
    else:
         print(f"  ❌ Failed to detect/tokenise Patient. Result: {result_text}")
         sys.exit(1)

    if "[[STREET_ADDRESS-01]]" in result_text:
        print("  ✅ Street Address got new counter type 01")
    else:
        print(f"  ❌ Failed to tokenise street address. Result: {result_text}")
        sys.exit(1)

    print("\n🎉 ALL COUNTER TOKEN TESTS PASSED!")

if __name__ == "__main__":
    test_counter_tokens()
