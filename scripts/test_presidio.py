
import sys
import os
import asyncio

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.presidio_deidentification_service import presidio_deidentification_service

def test_presidio():
    print("Testing Presidio De-identification Service...")
    
    text = "Patient John Doe (DOB: 05/15/1980) was admitted to General Hospital on 03/10/2025."
    print(f"Original: {text}")
    
    # 1. Analyze
    if not presidio_deidentification_service.analyzer:
        print("Presidio Analyzer not initialized!")
        return

    try:
        results = presidio_deidentification_service.analyzer.analyze(text=text, language="en")
        print(f"Analysis Results: Found {len(results)} entities")
        for res in results:
            print(f" - {res.entity_type}: {text[res.start:res.end]} ({res.score})")
            
        # 2. Anonymize (Simple)
        anonymized_result = presidio_deidentification_service.anonymizer.anonymize(
            text=text,
            analyzer_results=results
        )
        print(f"Anonymized: {anonymized_result.text}")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_presidio()
