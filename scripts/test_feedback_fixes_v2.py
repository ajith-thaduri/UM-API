import asyncio
import os
import sys
import re

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.presidio_deidentification_service import presidio_deidentification_service

async def test_feedback_cases():
    test_text = """
    Patient: John Michael Doe
    Known as Johnny Doe and Jane Doe too.
    Admitted to St. Mary's Regional Medical Center at 09:32 AM.
    Room number: Room 502 / Apt 5B.
    Lives in Springfield, IL 62704.
    Travelled to Illinois recently.
    Portal username: henrywalker82 / henry.matthews85
    File: henry_matthews_patient_photo_2026.jpg
    Coordinates: 39.7817 N, 89.6501 W
    Other Coord: Lat: 40.7128, Long: -74.0060
    MAC Address: 00:1B:44:11:3A:B7
    Age: 43 years old.
    Employer: Springfield Nuclear Power Plant.
    Insurance: Blue Cross Blue Shield of Illinois with ID BCBS-4433221100.
    """
    
    print("Original text:")
    print(test_text)
    
    # Run analysis
    results = presidio_deidentification_service.analyzer.analyze(
        text=test_text, language="en", score_threshold=0.35
    )
    
    print("\nDetected Entities:")
    for res in results:
        span = test_text[res.start:res.end].strip()
        print(f"Type: {res.entity_type}, Score: {res.score:.2f}, Text: '{span}'")

    # Process de-identification
    token_map = {}
    de_id_output = presidio_deidentification_service._process_residual_phi_in_string(
        test_text, results, token_map, 0, 0.35
    )
    
    print("\nDe-identified text:")
    print(de_id_output)
    
    # Checks
    print("\n--- Checks ---")
    
    # Check 1: Hospital (St. Mary's)
    if "Mary's Regional Medical Center" in de_id_output:
        print("❌ Hospital Leak (Partial)")
    else:
        print("✅ Hospital Redacted")
        
    # Check 2: Username
    if "henrywalker82" in de_id_output or "henry.matthews85" in de_id_output:
        print("❌ Username Leak")
    else:
        print("✅ Username Redacted")
        
    # Check 3: Filename
    if ".jpg" in de_id_output:
        print("❌ Filename Leak")
    else:
        print("✅ Filename Redacted")
        
    # Check 4: Time
    if "09:32 AM" in de_id_output:
        print("❌ Time Leak")
    else:
        print("✅ Time Redacted")
        
    # Check 5: ZIP 3-digit mask
    if "62704" in de_id_output:
        print("❌ ZIP Code exposed")
    elif "627**" in de_id_output:
        print("✅ ZIP Code masked (627**)")
    else:
        print("⚠️ ZIP Code not found or redacted differently")
        
    # Check 6: Age < 90
    if "43 years old" in de_id_output:
        print("✅ Age 43 preserved (as intended)")
    elif "[[REDACTED]]" in de_id_output and "years old" not in de_id_output:
        print("❌ Age 43 over-redacted")
        
    # Check 7: Coordinates
    if "39.7817" in de_id_output or "89.6501" in de_id_output or "40.7128" in de_id_output:
        print("❌ Coordinates Leak")
    else:
        print("✅ Coordinates Redacted")

    # Check 8: MAC Address
    if "00:1B:44:11:3A:B7" in de_id_output:
        print("❌ MAC Address Leak")
    else:
        print("✅ MAC Address Redacted")

    # Check 9: Room/Apt
    if "Room 502" in de_id_output or "Apt 5B" in de_id_output:
        print("❌ Room/Apt Leak")
    else:
        print("✅ Room/Apt Redacted")

if __name__ == "__main__":
    asyncio.run(test_feedback_cases())
