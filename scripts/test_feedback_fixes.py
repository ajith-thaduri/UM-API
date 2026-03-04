import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.presidio_deidentification_service import presidio_deidentification_service

async def run_feedback_test():
    test_text = """
    Patient: John Michael Doe
    Known as Johnny Doe and Jane Doe too.
    Admitted to St. Mary's Regional Medical Center.
    NPI: 1548273645
    Website: myhealthportal.com
    Portal URL: https://myportal.org/login
    Blog URL: http://blog.hospital.com
    LinkedIn URL: linkedin.com/in/robert
    Hospital Encounter Information Hospital
    Physician Phone and Physician Email
    Robert A. Henderson and Dr. Robert A. Henderson
    CVS Pharmacy
    Springfield Nuclear Power Plant
    Blue Cross Blue Shield of Illinois
    Moved to Illinois
    USA
    Midwest Logistics Corporation
    Patient photo filename: henry_matthews_patient_photo_2026.jpg
    Credit card number: 4532-8890-1123-4490
    Apartment 5B
    MAC Address: 00:1B:44:11:3A:B7
    Username: henrywalker82 / henry.matthews85
    192.168.1.45
    Green Valley Medical Center Hospital
    LOCATION: 30 AM with Dr
    """

    print("--- RAW PRESIDIO ENTITIES ---")
    results = presidio_deidentification_service.analyzer.analyze(
        text=test_text, language="en", score_threshold=0.35
    )
    for r in results:
        print(f"{r.entity_type:20} | {r.score:.2f} | {test_text[r.start:r.end].strip()}")

    print("\n--- AFTER SANITIZATION ---")
    sanitized = presidio_deidentification_service._sanitize_ner_results(results, test_text)
    for r in sanitized:
        print(f"{r.entity_type:20} | {r.score:.2f} | {test_text[r.start:r.end].strip()}")

if __name__ == "__main__":
    asyncio.run(run_feedback_test())
