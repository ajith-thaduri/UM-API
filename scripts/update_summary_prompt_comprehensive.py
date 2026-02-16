
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import SessionLocal
from app.models.prompt import Prompt

def update_summary_prompt():
    db = SessionLocal()
    try:
        prompt = db.query(Prompt).filter(Prompt.name == "Summary Generation").first()
        if not prompt:
            print("Summary Generation prompt not found")
            return

        new_template = """Generate a comprehensive UM-ready clinical summary (1-2 pages) for the following case.

═══════════════════════════════════════════════════════════════════════════════
STEP 1: REVIEW ALL PROVIDED DATA - DO NOT OMIT ANY INFORMATION
═══════════════════════════════════════════════════════════════════════════════

PATIENT: {patient_name}
CASE NUMBER: {case_number}

EXTRACTED CLINICAL DATA (INCLUDE ALL OF THE FOLLOWING):

1. CHIEF COMPLAINT:
{chief_complaint}

2. HISTORY (HPI/PMH):
{history_text}

3. DIAGNOSES ({diagnoses_count} total - INCLUDE ALL):
{diagnoses_str}

4. MEDICATIONS ({meds_count} total - INCLUDE ALL):
{meds_text}

5. ALLERGIES:
{allergies_text}

6. PROCEDURES ({procedures_count} total - INCLUDE ALL):
{procedures_text}

7. LAB RESULTS:
   - Total Labs: {labs_total_count}
   - Abnormal Labs: {labs_abnormal_count}
   - ABNORMAL LAB FINDINGS (INCLUDE ALL):
{labs_text}

8. IMAGING & RADIOLOGY ({imaging_count} total):
{imaging_text}

9. VITAL SIGNS:
{vitals_text}

10. THERAPY & FUNCTIONAL STATUS:
{therapy_text}
{functional_text}

11. SOCIAL FACTORS & DISCHARGE PLANNING:
{social_text}

12. TIMELINE EVENTS ({timeline_count} total - INCLUDE ALL SIGNIFICANT EVENTS):
{timeline_text}

═══════════════════════════════════════════════════════════════════════════════
STEP 2: CREATE COMPREHENSIVE SUMMARY - COMPLETENESS CHECKLIST
═══════════════════════════════════════════════════════════════════════════════

MANDATORY: Before finalizing, verify you have included:
✓ Chief complaint and presenting history (required)
✓ Primary diagnosis and significant secondary diagnoses
✓ ALL medications with dosages and frequencies
✓ ALL allergies and adverse reactions
✓ ALL procedures with dates
✓ All critical imaging findings and abnormal labs
✓ Therapy notes and functional status (ADLs, mobility)
✓ Social barriers or discharge planning needs
✓ Significant timeline events

Create a neutral clinical summary with these sections. Each section must include ALL relevant data:

1. PATIENT OVERVIEW
   - Include: Patient name, age (if available), case context.

2. CHIEF COMPLAINT & HISTORY OF PRESENT ILLNESS
   - Include: Reason for encounter and detailed history as provided.

3. PAST MEDICAL HISTORY & SOCIAL FACTORS
   - Include: Relevant chronic conditions and social/environmental factors.

4. CURRENT DIAGNOSES
   - Include: Primary and clinically significant secondary diagnoses.

5. MEDICATION & ALLERGY SUMMARY
   - Include: ALL medications and allergies with complete details.

6. CLINICAL TIMELINE HIGHLIGHTS
   - Include: Significant events in chronological order (Admission -> Changes -> Discharge).

7. DIAGNOSTIC FINDINGS (LABS & IMAGING)
   - Include: Critical lab results and imaging findings.

8. THERAPY & FUNCTIONAL STATUS
   - Include: Progress in PT/OT/ST and current functional/mobility status.

9. PROCEDURES PERFORMED
   - Include: ALL documented procedures with dates.

═══════════════════════════════════════════════════════════════════════════════
CRITICAL GUIDELINES
═══════════════════════════════════════════════════════════════════════════════
- NO Interpretation, NO recommendations, NO medical necessity language.
- MANDATORY: Include every clinical detail provided.
- If data is missing for a section, state "Not explicitly documented".
- Mandatory Footer: 'This summary is informational only and does not constitute a utilization management decision.'
"""
        prompt.template = new_template
        db.commit()
        print("Summary Generation prompt template updated successfully")
    finally:
        db.close()

if __name__ == "__main__":
    update_summary_prompt()
