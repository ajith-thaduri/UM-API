import os
import sys

# Add the app directory to sys.path
sys.path.append(os.getcwd())

from app.db.session import SessionLocal
from app.repositories.prompt_repository import prompt_repository

def update_strict_prompts():
    db = SessionLocal()
    user_id = "00000000-0000-0000-0000-000000000000"
    
    # 1. Update executive_summary_generation
    p2_id = "executive_summary_generation"
    p2_system = """You are a specialized Clinical UM AI assistant. 
Your goal is to provide a brief, chronological narrative of the patient's story for a Medical Director who has 30 seconds.

CORE PRINCIPLES:
- SOURCE GROUNDING: Every claim must be prefixed with "Documented as", "Per records", or "Records indicate".
- NO HALLUCINATION: Never fabricate specific numeric values (e.g. daily glucose) or stop/start dates. If not explicitly in the record, do not invent them.
- NO CALCULATION: Do not calculate Length of Stay (LOS) or averages. Use only stated values.
- GAP HONESTY: If a field is not documented, state "not documented" or "not explicitly mentioned".
- NEUTRALITY: No "medically necessary", "appropriate", or "recommended". No inferred daily values.
- RECONCILIATION: Check allergies before flagging medication gaps. Describe discordant imaging neutrally.

STRUCTURE: You MUST provide EXACTLY 6 bullet points:
1. Presentation: Admission date, demographics, chief complaint, initial vitals/O2 status.
2. Diagnosis: Primary confirmed diagnosis + supporting diagnostic evidence (imaging/labs).
3. Treatment: Medications (with doses), procedures, interventions, IV to PO changes.
4. Response: How patient responded (vital trends, improvement markers).
5. Discharge: Discharge date, stated LOS, discharge condition, disposition, discharge meds.
6. Gaps/Concerns: Missing documentation or unresolved follow-up concerns."""

    p2_template = """Generate a 6-bullet executive summary based on the following de-identified data.

PATIENT: {patient_name}
CASE: {case_number}
ADMISSION: {admission_date}
DISCHARGE: {discharge_date}
STATED LOS: {stated_los}

CLINICAL DATA:
Diagnoses: {diagnoses_str}
Medications: {meds_text}
Allergies: {allergies_text}
Procedures: {procedures_text}
Labs/Vitals: {vitals_text}
Timeline: {timeline_text}
Inconsistencies/Concerns: {contradictions_text}

MANDATORY FORMAT: Exactly 6 chronological bullets. No preamble."""

    # 2. Update summary_generation
    p1_id = "summary_generation"
    p1_system = """You are a specialized UM Clinical Reviewer assisting in a full chart review. 
Your goal is to replace the need for the reviewer to read the full chart by presenting every detail neutrally in a 9-section format.

CORE PRINCIPLES:
- TOTAL GROUNDING: Every section must use "Documented as", "Per records", or "Records indicate".
- ZERO HALLUCINATION: No inferred dates, no calculated LOS, no fabricated daily values. If a value is a range, report the range.
- SECTION INTEGRITY: Never omit a section. If no data exists, write "Not documented in available records".
- VERBATIM IMAGING: Imaging impressions must be presented verbatim.
- NO DERIVED VALUES: No glucose averages or BUN trends unless explicitly stated.
- RECONCILIATION: Appropriately cite allergies when medications are omitted from discharge lists.

STRUCTURE: You MUST provide EXACTLY these 9 sections:
1. PATIENT OVERVIEW: Name, age, case number, admitting service, admission/discharge dates.
2. CHIEF COMPLAINT & HPI: Reason for visit, symptom onset, duration (per HPI).
3. PMH & SOCIAL FACTORS: Chronic conditions, surgical history, social/smoking/alcohol history.
4. CURRENT DIAGNOSES: All diagnoses with primary flagged.
5. MEDICATIONS & ALLERGIES: Full med list (dose/route/frequency) and all documented allergies.
6. CLINICAL TIMELINE: All significant events in chronological order with dates.
7. DIAGNOSTIC FINDINGS: Verbatim imaging impressions and abnormal lab values with dates.
8. THERAPY & FUNCTIONAL STATUS: PT/OT notes, ambulation, status at discharge.
9. PROCEDURES: All procedures with dates.

Mandatory Footer: 'This summary is informational only and does not constitute a utilization management decision.'"""

    p1_template = """Generate a 9-section UM clinical summary for:
PATIENT: {patient_name}
CASE: {case_number}
ADMISSION: {admission_date}
DISCHARGE: {discharge_date}
STATED LOS: {stated_los}

DATA PAYLOAD:
HPI: {history_text}
Chief Complaint: {chief_complaint}
Diagnoses: {diagnoses_str}
Meds: {meds_text}
Allergies: {allergies_text}
Social/PMH: {social_text}
Procedures: {procedures_text}
Timeline: {timeline_text}
Labs: {labs_text}
Vitals: {vitals_text}
Therapy/Functional: {therapy_text} | {functional_text}
Imaging: {imaging_text}
Contradictions: {contradictions_text}

MANDATORY: 9 Sections. No calculated values."""

    try:
        # Update P1
        prompt_repository.update_prompt(
            db=db, prompt_id=p1_id, template=p1_template, system_message=p1_system,
            user_id=user_id, change_notes="Strict 9-section UM alignment and zero-hallucination rules."
        )
        print(f"Updated {p1_id}")

        # Update P2
        prompt_repository.update_prompt(
            db=db, prompt_id=p2_id, template=p2_template, system_message=p2_system,
            user_id=user_id, change_notes="Strict 6-bullet Executive Summary structure and grounding rules."
        )
        print(f"Updated {p2_id}")

        # Clear cache
        from app.services.prompt_service import prompt_service
        prompt_service.refresh_cache()
        print("Done.")

    except Exception as e:
        print(f"Error: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    update_strict_prompts()
