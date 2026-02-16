
import sys
import os
from pathlib import Path
from unittest.mock import MagicMock

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

def simulate_summary_generation_logic(presidio_enabled: bool, data: dict, patient_name: str):
    """
    Simulates the logic that will be added to SummaryService.
    """
    print(f"\n[Toggle State: Presidio {'ENABLED' if presidio_enabled else 'DISABLED'}]")
    
    if presidio_enabled:
        print("-> Running Presidio De-identification...")
        # Simulating de_identify_for_summary
        processed_data = {
            "patient": "[[PERSON-01]]",
            "clinical": data["clinical"].replace(patient_name, "[[PERSON-01]]")
        }
        print(f"-> Payload to Claude: {processed_data}")
        return processed_data
    else:
        print("-> BYPASSING Presidio (Sending RAW Data)...")
        # Direct pass-through
        processed_data = {
            "patient": patient_name,
            "clinical": data["clinical"]
        }
        print(f"-> Payload to Claude: {processed_data}")
        return processed_data

def test_toggle_cases():
    print("=== Testing Presidio Toggle Logic (Unit Test) ===")
    
    patient_name = "John Doe"
    raw_data = {
        "clinical": f"Patient {patient_name} with hypertension and diabetes."
    }
    
    # Scenario 1: Presidio ON (Compliance Mode)
    redacted = simulate_summary_generation_logic(presidio_enabled=True, data=raw_data, patient_name=patient_name)
    assert "[[PERSON-01]]" in redacted["clinical"]
    assert "John Doe" not in redacted["clinical"]
    print("✅ Scenario 1 Passed: Data was redacted.")
    
    # Scenario 2: Presidio OFF (Raw Mode)
    raw = simulate_summary_generation_logic(presidio_enabled=False, data=raw_data, patient_name=patient_name)
    assert "John Doe" in raw["clinical"]
    assert "[[PERSON-01]]" not in raw["clinical"]
    print("✅ Scenario 2 Passed: Data was sent raw.")

if __name__ == "__main__":
    test_toggle_cases()
