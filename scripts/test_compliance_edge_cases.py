
import sys
import os
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from app.services.presidio_deidentification_service import presidio_deidentification_service

def test_edge_cases():
    test_cases = [
        {
            "name": "Street Address Detection (Evergreen)",
            "text": "Patient lives at 742 Evergreen Terrace.",
            "should_detect": ["STREET_ADDRESS"],
            "should_not_detect": []
        },
        {
            "name": "Street Address Detection (Mayo)",
            "text": "Clinic at 5777 E Mayo Blvd.",
            "should_detect": ["STREET_ADDRESS"],
            "should_not_detect": []
        },
        {
            "name": "ZIP Code Detection (62704)",
            "text": "Zip code is 62704.",
            "should_detect": ["ZIP_CODE"],
            "should_not_detect": []
        },
        {
            "name": "ZIP Code Detection (85054)",
            "text": "Phoenix AZ 85054.",
            "should_detect": ["ZIP_CODE"],
            "should_not_detect": []
        },
        {
            "name": "NPI Detection",
            "text": "Provider NPI: 1548392017",
            "should_detect": ["NPI"],
            "should_not_detect": []
        },
        {
            "name": "City False Positive (Doctor MD)",
            "text": "Dr. Thompson, MD saw the patient.",
            "should_detect": ["PROVIDER"], # Thompson
            "should_not_detect": ["CITY"] # MD should NOT be a city
        },
        {
            "name": "Email vs Person Overlap",
            "text": "Contact michael.johnson65@gmail.com for details.",
            "should_detect": ["EMAIL_ADDRESS"],
            "should_not_detect": ["PERSON"] # "michael.johnson" inside email should NOT be PERSON
        },
        {
            "name": "Valid City State",
            "text": "Patient is from Phoenix, AZ.",
            "should_detect": ["CITY"],
            "should_not_detect": []
        }
    ]

    print("=== Testing Compliance Edge Cases ===\n")
    
    failures = 0
    
    for case in test_cases:
        print(f"Testing: {case['name']}")
        text = case["text"]
        
        # We need to access the analyzer directly or mock the de-identify flow
        # easier to use the internal _process_single_string equivalent logic
        # OR just call analyze directly since we want to check detections
        
        results = presidio_deidentification_service.analyzer.analyze(text=text, language='en', score_threshold=0.35)
        
        # Apply the overlap filter manually as it's done in the service
        results = presidio_deidentification_service._filter_email_person_overlap(results)
        
        detected_types = [r.entity_type for r in results]
        
        passed = True
        
        # Check expected detections
        for entity in case["should_detect"]:
            if entity not in detected_types:
                print(f"  ❌ FAILED: Expected {entity}, found {detected_types}")
                passed = False
        
        # Check unwanted detections
        for entity in case["should_not_detect"]:
            if entity in detected_types:
                print(f"  ❌ FAILED: Did NOT expect {entity}, found it.")
                passed = False
                
        if passed:
            print("  ✅ PASSED")
        else:
            failures += 1
        print("-" * 30)

    if failures == 0:
        print("\n🎉 ALL COMPLIANCE EDGE CASES PASSED!")
        sys.exit(0)
    else:
        print(f"\n❌ {failures} TESTS FAILED.")
        sys.exit(1)

if __name__ == "__main__":
    test_edge_cases()
