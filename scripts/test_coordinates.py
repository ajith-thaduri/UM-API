import asyncio
import os
import sys

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.presidio_deidentification_service import presidio_deidentification_service

async def test_coordinates():
    test_text = """
    Patient location recorded at Lat: 40.7128, Long: -74.0060.
    Another point: 34.0522, -118.2437.
    DMS representation: 40° 42' 46" N, 74° 0' 21" W.
    """
    
    print(f"Original text:\n{test_text}")
    
    results = presidio_deidentification_service.analyzer.analyze(
        text=test_text,
        language="en",
        score_threshold=0.5
    )
    
    print("\nDetected Entities:")
    for res in results:
        print(f"Type: {res.entity_type}, Score: {res.score}, Text: '{test_text[res.start:res.end]}'")

    # Process de-identification
    # Mocking necessary bits for de-identify_for_summary_async might be complex
    # Let's just test the residual phi processing
    de_id_text = presidio_deidentification_service._process_residual_phi_in_string(
        test_text, results, {}, 0, 0.5
    )
    
    print(f"\nDe-identified text:\n{de_id_text}")

if __name__ == "__main__":
    asyncio.run(test_coordinates())
