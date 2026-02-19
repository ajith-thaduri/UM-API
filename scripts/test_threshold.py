import sys
import os
sys.path.append(os.getcwd())
from app.services.presidio_deidentification_service import presidio_deidentification_service

def test_threshold():
    text = "The MRN is 458921. Appointment at 09:00 AM."
    # MRN recognizer has score 0.95
    # Time recognizer has score 0.95
    
    print("\n--- Threshold 0.9 ---")
    results = presidio_deidentification_service.analyzer.analyze(text=text, language='en', score_threshold=0.9)
    for r in results:
        print(f"{r.entity_type}: {r.score}")
    
    print("\n--- Threshold 0.99 ---")
    results = presidio_deidentification_service.analyzer.analyze(text=text, language='en', score_threshold=0.99)
    if not results:
        print("No results (Correct!)")
    for r in results:
        print(f"{r.entity_type}: {r.score}")

if __name__ == "__main__":
    test_threshold()
