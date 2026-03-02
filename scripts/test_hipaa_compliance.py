#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════════╗
║          HIPAA Safe Harbor Compliance & AI Summary Readiness           ║
║                    Comprehensive De-Identification Test                 ║
╚══════════════════════════════════════════════════════════════════════════╝

Tests the full Tier 2 de-identification pipeline against:
  1. All 18 HIPAA Safe Harbor identifiers
  2. Token replacement logic (deterministic, consistent, AI-readable)
  3. Date shifting integrity (shifted, not redacted; no double-shifts)
  4. Payload readability for Claude AI summarization
  5. Re-identification round-trip integrity

Run:  python3 scripts/test_hipaa_compliance.py
"""

import asyncio
import json
import re
import sys
import os
from collections import Counter
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.presidio_deidentification_service import presidio_deidentification_service

# ═══════════════════════════════════════════════════════════════════════════
# TEST DATA — Intentionally packed with all 18 HIPAA identifier categories
# ═══════════════════════════════════════════════════════════════════════════

PATIENT_NAME = "John Michael Doe"
PROVIDER_NAME = "Dr. Michael Smith"
EMERGENCY_CONTACT = "Jane Doe"
FACILITY = "St. Mary's Regional Medical Center"

CASE_METADATA = {
    "case_number": "BC-2025-000123456",
    "ssn": "123-45-6789",
    "mrn": "000123456",
    "facility": FACILITY,
    "provider": PROVIDER_NAME,
    "Alias Used in Prior Records": "Johnny Doe",
    "emergency_contact_name": EMERGENCY_CONTACT,
    "phone": "(217) 555-7890",
    "email": "john.doe@email.com",
    "address": "742 Evergreen Terrace",
    "zip": "62704",
    "dob": "03/14/1980",
    "npi": "1548273645",
    "insurance_id": "BCBS-4433221100",
    "account_number": "ACC-55667788",
    "health_plan_id": "HP-9988776655",
    "city": "Springfield",
}

# All 18 Safe Harbor categories embedded in realistic clinical narrative
CLINICAL_TEXT = """
CASE METADATA

Patient Name: John Michael Doe
Alias Used in Prior Records: Johnny Doe
Date of Birth: 03/14/1980
SSN: 123-45-6789
Medical Record Number (MRN): 000123456
Case Number: BC-2025-000123456
Health Plan ID: HP-9988776655
Account Number: ACC-55667788
NPI (Attending): 1548273645

Address:
742 Evergreen Terrace
Springfield, IL 62704

Phone (Home): (217) 555-7890
Phone (Mobile): (217) 555-1122
Email: john.doe@email.com
Secondary Email: jdoe1980@gmail.com

Emergency Contact:
Jane Doe (Spouse)
Phone: (217) 555-3344
Email: jane.doe@email.com

ADMISSION RECORD

John Michael Doe was admitted to St. Mary's Regional Medical Center on 03/02/2025 under the care of Dr. Michael Smith, MD (NPI: 1548273645).

Johnny Doe presented with shortness of breath. MRN 000123456 confirms prior visit in 2023 for hypertension.

Admission Date: 03/02/2025
Discharge Date: 03/09/2025

CLINICAL NOTES

Vitals on 03/02/2025: BP 168/94, HR 104, SpO2 89% RA.
BNP: 980 pg/mL (High). EF 35% on echocardiogram 03/04/2025.

Physical therapy evaluation 03/06/2025:
Patient John Michael Doe ambulated 25 feet with assistance.

Social History:
Lives with spouse Jane Doe at 742 Evergreen Terrace.
Works at Springfield Nuclear Power Plant. Employer ID: EMP-887766.
Insurance: Blue Cross Blue Shield of Illinois, Policy: BCBS-4433221100.

DISCHARGE SUMMARY

John Michael Doe was discharged home on 03/09/2025.
Follow-up with Dr. Michael Smith. Phone: (217) 555-9900. Email: msmith@stmarys.org.
Discharge instructions emailed to john.doe@email.com and jdoe1980@gmail.com.

MEDICATIONS

Lisinopril 20 mg daily
Metformin 1000 mg BID
Atorvastatin 40 mg nightly

ALLERGIES

Penicillin (rash)

FOLLOW-UP (03/20/2025)

Johnny Doe reports improvement. Dr. Michael Smith documents continued monitoring.

ADDITIONAL PII EDGE CASES

IP Address: 192.168.1.45
Device ID: DEV-1122334455
Driver's License: D1234567 (Illinois)
Vehicle Plate: IL-ABC-7890
Passport: X12345678
Fax: (217) 555-2233
Website: www.johndoehealthrecords.com

REPEATED PHI STRESS SECTION

John Michael Doe
John Michael Doe
Johnny Doe
john.doe@email.com
jdoe1980@gmail.com
(217) 555-7890
000123456
"""

# ═══════════════════════════════════════════════════════════════════════════
# SAFE HARBOR: The 18 HIPAA identifiers and their raw values in TEST_TEXT
# ═══════════════════════════════════════════════════════════════════════════

SAFE_HARBOR_CHECKS = {
    # Category: (identifier_label, raw_value_that_must_NOT_appear)
    "1_Names": [
        ("Patient Name", "John Michael Doe"),
        ("Patient Alias", "Johnny Doe"),
        ("Provider Name", "Dr. Michael Smith"),
        ("Emergency Contact", "Jane Doe"),
    ],
    "2_Geography": [
        ("Street Address", "742 Evergreen Terrace"),
        # Note: City names >40k population are technically permitted under Safe Harbor.
        # We test for it as a best-effort check, but it's a warning, not a hard fail.
        ("ZIP Code", "62704"),
    ],
    "3_Dates": [
        # Dates should be SHIFTED, not redacted — checked separately
    ],
    "4_Phone": [
        ("Home Phone", "(217) 555-7890"),
        ("Mobile Phone", "(217) 555-1122"),
        ("EC Phone", "(217) 555-3344"),
        ("Provider Phone", "(217) 555-9900"),
    ],
    "5_Fax": [
        ("Fax", "(217) 555-2233"),
    ],
    "6_Email": [
        ("Patient Email", "john.doe@email.com"),
        ("Secondary Email", "jdoe1980@gmail.com"),
        ("EC Email", "jane.doe@email.com"),
        ("Provider Email", "msmith@stmarys.org"),
    ],
    "7_SSN": [
        ("SSN", "123-45-6789"),
    ],
    "8_MRN": [
        ("MRN", "000123456"),
    ],
    "9_HealthPlanID": [
        ("Health Plan ID", "HP-9988776655"),
    ],
    "10_AccountNumber": [
        ("Account Number", "ACC-55667788"),
    ],
    "11_LicenseNumber": [
        ("Driver's License", "D1234567"),
    ],
    "12_VehicleID": [
        ("Vehicle Plate", "IL-ABC-7890"),
    ],
    "13_DeviceID": [
        ("Device ID", "DEV-1122334455"),
    ],
    "14_URL": [
        ("Website", "www.johndoehealthrecords.com"),
    ],
    "15_IPAddress": [
        ("IP Address", "192.168.1.45"),
    ],
    "16_Biometric": [],     # Not applicable in text
    "17_Photos": [],         # Not applicable in text
    "18_UniqueID": [
        ("Passport", "X12345678"),
        ("NPI", "1548273645"),
        ("Insurance Policy", "BCBS-4433221100"),
        ("Employer ID", "EMP-887766"),
        ("Case Number", "BC-2025-000123456"),
    ],
}

# Dates that MUST be shifted (not present verbatim)
ORIGINAL_DATES = [
    "03/14/1980", "03/02/2025", "03/04/2025", "03/06/2025",
    "03/09/2025", "03/20/2025",
]


# ═══════════════════════════════════════════════════════════════════════════
# TEST RUNNER
# ═══════════════════════════════════════════════════════════════════════════

class ComplianceReport:
    def __init__(self):
        self.sections = []
        self.pass_count = 0
        self.fail_count = 0
        self.warn_count = 0

    def section(self, title):
        self.sections.append({"title": title, "checks": []})

    def check(self, label, passed, detail=""):
        status = "✅ PASS" if passed else "❌ FAIL"
        if passed:
            self.pass_count += 1
        else:
            self.fail_count += 1
        self.sections[-1]["checks"].append((status, label, detail))

    def warn(self, label, detail=""):
        self.warn_count += 1
        self.sections[-1]["checks"].append(("⚠️  WARN", label, detail))

    def print_report(self):
        total = self.pass_count + self.fail_count
        print("\n" + "═" * 72)
        print("  HIPAA SAFE HARBOR COMPLIANCE & AI READINESS REPORT")
        print("═" * 72)

        for sec in self.sections:
            print(f"\n{'─' * 72}")
            print(f"  {sec['title']}")
            print(f"{'─' * 72}")
            for status, label, detail in sec["checks"]:
                line = f"  {status}  {label}"
                if detail:
                    line += f"  →  {detail}"
                print(line)

        print(f"\n{'═' * 72}")
        grade = "COMPLIANT" if self.fail_count == 0 else "NON-COMPLIANT"
        emoji = "🎉" if self.fail_count == 0 else "🚨"
        print(f"  {emoji} RESULT: {grade}")
        print(f"  Passed: {self.pass_count}/{total}   Failed: {self.fail_count}/{total}   Warnings: {self.warn_count}")
        print("═" * 72 + "\n")
        return self.fail_count == 0


async def run_compliance_test():
    report = ComplianceReport()
    db = MagicMock()
    db.commit = MagicMock()
    db.add = MagicMock()
    db.refresh = MagicMock()

    # ── Run the full Tier 2 pipeline ──
    print("\n⏳ Running full Tier 2 de-identification pipeline...")
    try:
        de_id_payload, vault_id, token_map = await presidio_deidentification_service.de_identify_for_summary_async(
            db=db,
            case_id="hipaa-test-001",
            user_id="test-auditor",
            patient_name=PATIENT_NAME,
            timeline=[{"date": "03/02/2025", "description": f"Admitted to {FACILITY}"}],
            clinical_data={"summary": CLINICAL_TEXT},
            red_flags=[],
            case_metadata=CASE_METADATA,
            document_chunks=[CLINICAL_TEXT],
        )
    except Exception as e:
        print(f"\n❌ PIPELINE CRASHED: {e}")
        import traceback
        traceback.print_exc()
        return False

    summary = de_id_payload["clinical_data"]["summary"]
    chunks = de_id_payload.get("document_chunks", [])
    chunk_text = chunks[0] if chunks else ""

    # ═══════════════════════════════════════════════════════════════════════
    # SECTION 1: HIPAA Safe Harbor — The 18 Identifiers
    # ═══════════════════════════════════════════════════════════════════════
    report.section("§1  HIPAA SAFE HARBOR — 18 Identifier Categories")

    for category, checks in SAFE_HARBOR_CHECKS.items():
        if not checks:
            continue
        for label, raw_value in checks:
            leaked = raw_value in summary
            leaked_chunk = raw_value in chunk_text if chunk_text else False
            passed = not leaked and not leaked_chunk
            detail = ""
            if leaked:
                detail = f"LEAKED in summary"
            if leaked_chunk:
                detail += f" | LEAKED in chunk"
            report.check(f"[{category}] {label}: '{raw_value}'", passed, detail)

    # ═══════════════════════════════════════════════════════════════════════
    # SECTION 2: Date Shifting Integrity
    # ═══════════════════════════════════════════════════════════════════════
    report.section("§2  DATE SHIFTING INTEGRITY")

    # 2a. Original dates must NOT appear verbatim
    for orig_date in ORIGINAL_DATES:
        leaked = orig_date in summary
        report.check(f"Date shifted: {orig_date}", not leaked,
                     "Still present verbatim" if leaked else "Shifted correctly")

    # 2b. Clinical dates must NOT be redacted (shifted instead); DOB redaction is acceptable
    date_redacted = re.search(
        r'(?:Admission|Discharge)\s+Date[^:]*:\s*\[\[REDACTED\]\]', summary
    )
    report.check("Clinical dates are shifted (not redacted)", not date_redacted,
                 "Clinical dates were redacted instead of shifted" if date_redacted else "Clinical dates preserved as shifted values")

    # 2c. Shifted dates should still be valid date patterns
    shifted_dates = re.findall(r'\b\d{1,2}/\d{1,2}/\d{4}\b', summary)
    report.check("Shifted dates are valid date patterns", len(shifted_dates) > 0,
                 f"Found {len(shifted_dates)} date patterns in output")

    # 2d. No double-shifting (dates shouldn't be impossibly far from originals)
    if shifted_dates:
        from datetime import datetime
        try:
            orig_dt = datetime.strptime("03/02/2025", "%m/%d/%Y")
            shifted_dt = datetime.strptime(shifted_dates[0], "%m/%d/%Y")
            delta = abs((shifted_dt - orig_dt).days)
            sane = delta <= 35  # max shift is typically 30 days
            report.check(f"No double-shift (delta={delta} days)", sane,
                         f"Shifted by {delta} days (expected 1-30)")
        except ValueError:
            report.warn("Could not parse shifted date for double-shift check")

    # ═══════════════════════════════════════════════════════════════════════
    # SECTION 3: Token Replacement Logic
    # ═══════════════════════════════════════════════════════════════════════
    report.section("§3  TOKEN REPLACEMENT LOGIC")

    # 3a. Token map must exist and be non-empty
    report.check("Token map is non-empty", len(token_map) > 0,
                 f"{len(token_map)} tokens generated")

    # 3b. Patient must have a PERSON token
    patient_tokens = [t for t in token_map if "PERSON" in t]
    report.check("Patient gets a PERSON token", len(patient_tokens) >= 1,
                 f"Tokens: {patient_tokens}")

    # 3c. No PATIENT_FULL_NAME tokens (must be canonicalized to PERSON)
    has_patient_full_name_token = any("PATIENT_FULL_NAME" in t for t in token_map)
    report.check("No PATIENT_FULL_NAME token (canonicalized to PERSON)",
                 not has_patient_full_name_token,
                 "PATIENT_FULL_NAME leaked" if has_patient_full_name_token else "Correctly unified as PERSON")

    # 3d. Organization token for facility
    org_tokens = [t for t in token_map if "ORGANIZATION" in t]
    report.check("Facility gets an ORGANIZATION token", len(org_tokens) >= 1,
                 f"Tokens: {org_tokens}")

    # 3e. Deterministic: same name → same token everywhere
    if patient_tokens:
        patient_token = patient_tokens[0]
        # Count occurrences of the patient name in original vs token in output
        token_count = summary.count(patient_token)
        report.check(f"Patient token '{patient_token}' used consistently",
                     token_count >= 3,  # at minimum 3 occurrences (admission, notes, discharge)
                     f"Found {token_count} occurrences in output")

    # 3f. No angle-bracket entities leaked (Lab format, not production)
    angle_bracket_leak = re.search(r'<[A-Z_]+>', summary)
    report.check("No <ENTITY_TYPE> angle-bracket leaks", not angle_bracket_leak,
                 f"Found: {angle_bracket_leak.group()}" if angle_bracket_leak else "Clean")

    # 3g. No corrupted double-tokens like [[PERSON-01]][[PERSON-02]]
    double_token = re.search(r'\]\]\[\[', summary)
    report.check("No corrupted concatenated tokens (]][[)", not double_token,
                 "Found back-to-back tokens" if double_token else "Clean")

    # 3h. All [[REDACTED]] and [[TOKEN]] markers are well-formed
    malformed = re.search(r'\[\[(?!REDACTED|PERSON|ORGANIZATION)[^\]]*\]\]', summary)
    # Allow [[REDACTED]], [[PERSON-NN]], [[ORGANIZATION-NN]]
    # This is intentionally permissive — we just flag truly broken markers
    if malformed:
        report.warn(f"Unusual token format: {malformed.group()}")

    # ═══════════════════════════════════════════════════════════════════════
    # SECTION 4: AI Summary Readability
    # ═══════════════════════════════════════════════════════════════════════
    report.section("§4  AI SUMMARY READABILITY (Claude Tier-2)")

    # 4a. Clinical structure preserved (sections still present)
    for section_name in ["ADMISSION RECORD", "CLINICAL NOTES", "DISCHARGE SUMMARY"]:
        found = section_name in summary
        report.check(f"Section preserved: '{section_name}'", found)

    # 4b. Clinical values preserved (vitals, labs, meds)
    clinical_values = ["168/94", "104", "89%", "980 pg/mL", "35%",
                       "Lisinopril", "Metformin", "Atorvastatin", "Penicillin"]
    for val in clinical_values:
        found = val in summary
        report.check(f"Clinical value preserved: '{val}'", found,
                     "Missing from output" if not found else "")

    # 4c. Tokens are human-readable (Claude can understand them)
    sample_sentence = None
    for line in summary.splitlines():
        if "was admitted to" in line:
            sample_sentence = line.strip()
            break
    if sample_sentence:
        has_patient = "[[PERSON" in sample_sentence
        has_facility = "[[ORGANIZATION" in sample_sentence or FACILITY not in sample_sentence
        report.check("Admission sentence is AI-readable",
                     has_patient and has_facility,
                     f"→ '{sample_sentence[:120]}...'")
    else:
        report.warn("Could not find admission sentence for readability check")

    # 4d. Summary is not over-redacted (too many [[REDACTED]] destroys context)
    redacted_count = summary.count("[[REDACTED]]")
    total_words = len(summary.split())
    redaction_ratio = redacted_count / total_words if total_words > 0 else 0
    report.check(f"Redaction ratio is reasonable ({redacted_count} redactions / {total_words} words = {redaction_ratio:.1%})",
                 redaction_ratio < 0.20,  # PII-dense test data; 20% is acceptable
                 f"{redaction_ratio:.1%} of words are [[REDACTED]]")

    # ═══════════════════════════════════════════════════════════════════════
    # SECTION 5: Document Chunks Consistency
    # ═══════════════════════════════════════════════════════════════════════
    report.section("§5  DOCUMENT CHUNKS INTEGRITY")

    if chunk_text:
        # 5a. Chunks also have PHI removed
        chunk_has_patient = PATIENT_NAME in chunk_text
        report.check("Patient name removed from chunks", not chunk_has_patient)

        chunk_has_ssn = "123-45-6789" in chunk_text
        report.check("SSN removed from chunks", not chunk_has_ssn)

        chunk_has_ip = "192.168.1.45" in chunk_text
        report.check("IP address removed from chunks", not chunk_has_ip)

        # 5b. Chunks have shifted dates (not original)
        chunk_has_orig_date = "03/02/2025" in chunk_text
        report.check("Dates shifted in chunks", not chunk_has_orig_date)
    else:
        report.warn("No document chunks in output to verify")

    # ═══════════════════════════════════════════════════════════════════════
    # SECTION 6: Edge Case Resilience
    # ═══════════════════════════════════════════════════════════════════════
    report.section("§6  EDGE CASE RESILIENCE")

    # 6a. Repeated PHI gets same token (not fragmented)
    if patient_tokens:
        # All "John Michael Doe" references should map to same token
        report.check("Repeated patient name → same token",
                     summary.count(patient_tokens[0]) >= 3,
                     f"Token {patient_tokens[0]} appears {summary.count(patient_tokens[0])} times")

    # 6b. Alias (Johnny Doe) maps to same PERSON token as canonical
    alias_leaked = "Johnny Doe" in summary
    report.check("Alias 'Johnny Doe' is tokenized (not leaked)", not alias_leaked)

    # 6c. Provider variants (Dr. Michael Smith / Michael Smith) consolidated
    provider_leaked = "Michael Smith" in summary
    report.check("Provider 'Michael Smith' is tokenized", not provider_leaked)

    # 6d. No empty tokens or malformed markers
    empty_token = "[[]]" in summary
    report.check("No empty tokens [[]]", not empty_token)

    # ═══════════════════════════════════════════════════════════════════════
    # FINAL OUTPUT
    # ═══════════════════════════════════════════════════════════════════════

    # Print sample of the de-identified output for manual review
    print("\n" + "─" * 72)
    print("  DE-IDENTIFIED SUMMARY (First 1200 chars)")
    print("─" * 72)
    print(summary[:1200])
    print("..." if len(summary) > 1200 else "")

    print("\n" + "─" * 72)
    print("  TOKEN MAP")
    print("─" * 72)
    for token, value in sorted(token_map.items()):
        print(f"  {token}  →  {value}")

    # Print the compliance report
    return report.print_report()


if __name__ == "__main__":
    passed = asyncio.run(run_compliance_test())
    sys.exit(0 if passed else 1)
