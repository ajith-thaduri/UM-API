"""End-to-end test for Safe Harbor identifiers in the de-identified payload."""
import asyncio, sys
sys.path.append("/Users/ajiththaduri/Desktop/V2/UM-API")
from app.services.presidio_deidentification_service import presidio_deidentification_service as svc
from unittest.mock import MagicMock

METADATA = {
    "case_number": "BC-2025-000123456",
    "ssn": "123-45-6789",
    "mrn": "000123456",
    "facility": "St. Mary's Regional Medical Center",
    "provider": "Dr. Michael Smith",
}
CLINICAL = {
    "summary": (
        "SSN: 123-45-6789\n"
        "IP Address: 192.168.1.45\n"
        "Driver's License: D1234567 (Illinois)\n"
        "Vehicle Plate: IL-ABC-7890\n"
        "Passport: X12345678\n"
        "John Michael Doe was treated at St. Mary's on 03/02/2025."
    )
}

async def run():
    db = MagicMock()
    payload, vault_id, token_map = await svc.de_identify_for_summary_async(
        db=db, case_id="test-sh", user_id="u1",
        patient_name="John Michael Doe",
        timeline=[], clinical_data=CLINICAL,
        red_flags=[], case_metadata=METADATA,
        document_chunks=[CLINICAL["summary"]],
    )
    summary = payload["clinical_data"]["summary"]
    print("=== De-identified Safe Harbor Section ===")
    for line in summary.splitlines()[:10]:
        print(" ", line)

    checks = [
        ("SSN 123-45-6789", "123-45-6789"),
        ("IP 192.168.1.45", "192.168.1.45"),
        ("License D1234567", "D1234567"),
        ("Vehicle IL-ABC-7890", "IL-ABC-7890"),
        ("Passport X12345678", "X12345678"),
    ]
    print("\n=== HIPAA Safe Harbor Check ===")
    all_pass = True
    for label, raw in checks:
        if raw in summary:
            print(f"  ❌ LEAK {label}: '{raw}' still present")
            all_pass = False
        else:
            print(f"  ✅ CLEAN {label}")

    # PATIENT_FULL_NAME canonicalization
    if "PATIENT_FULL_NAME" in str(token_map):
        print("  ❌ PATIENT_FULL_NAME token leaked — not canonicalized to PERSON")
    else:
        print("  ✅ PATIENT_FULL_NAME canonicalized to PERSON")

    print("\n" + ("🎉 ALL SAFE HARBOR CHECKS PASSED" if all_pass else "⚠️  SOME CHECKS FAILED"))

asyncio.run(run())
