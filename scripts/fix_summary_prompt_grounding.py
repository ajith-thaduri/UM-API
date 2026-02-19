#!/usr/bin/env python3
"""
Script to update summary prompt with grounding-focused instructions.
Removes completeness pressure and adds explicit documentation-based language.
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import SessionLocal
from app.models.prompt import Prompt
from datetime import datetime, timezone

def update_summary_prompt():
    """Update summary prompt with grounding-focused template"""
    
    db = SessionLocal()
    try:
        prompt = db.query(Prompt).filter(Prompt.id == "summary_generation").first()
        
        if not prompt:
            print("❌ Summary Generation prompt not found")
            return
        
        print("Updating summary_generation prompt with grounding focus...")
        
        # New grounding-focused template
        new_template = """Generate a comprehensive UM-ready clinical summary (1-2 pages) for the following case.

═══════════════════════════════════════════════════════════════════════════════
STEP 1: REVIEW PROVIDED DATA - REPORT ONLY WHAT IS EXPLICITLY DOCUMENTED
═══════════════════════════════════════════════════════════════════════════════

PATIENT: {patient_name}
CASE NUMBER: {case_number}

EXTRACTED CLINICAL DATA (Report all documented information):

1. CHIEF COMPLAINT:
{chief_complaint}

2. HISTORY (HPI/PMH):
{history_text}

3. DIAGNOSES ({diagnoses_count} total - report all documented):
{diagnoses_str}

4. MEDICATIONS ({meds_count} total - report all documented):
{meds_text}

5. ALLERGIES:
{allergies_text}

6. PROCEDURES ({procedures_count} total - report all documented):
{procedures_text}

7. LAB RESULTS:
   - Total Labs: {labs_total_count}
   - Abnormal Labs: {labs_abnormal_count}
   - ABNORMAL LAB FINDINGS (report all documented):
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

12. TIMELINE EVENTS ({timeline_count} total - report significant documented events):
{timeline_text}

═══════════════════════════════════════════════════════════════════════════════
STEP 2: CREATE SUMMARY - GROUNDING PRINCIPLES
═══════════════════════════════════════════════════════════════════════════════

GROUNDING RULES (CRITICAL):
- This summary is based on EXTRACTED data, which may be incomplete
- Report ONLY information explicitly present in the extraction data above
- If key information (admission date, discharge date, etc.) is missing from extracted data, state "Not documented in available extraction"
- Do not infer or calculate values not provided (e.g., don't calculate length of stay if dates are missing)
- Do not assume medication changes, lab trends, or clinical decisions
- Present information as "documented" or "recorded as" to indicate source-bound nature
- If data appears incomplete or contradictory, note: "Based on available documentation..." or "Per documented records..."

COMPLETENESS PRINCIPLE:
Report clinical details that ARE in the extraction data. If sections have limited data, acknowledge this rather than inventing details.

Create a neutral clinical summary with these sections:

1. PATIENT OVERVIEW
   - Include: Patient name, age (if available), case context from available data.

2. CHIEF COMPLAINT & HISTORY OF PRESENT ILLNESS
   - Include: Reason for encounter and detailed history as documented.

3. PAST MEDICAL HISTORY & SOCIAL FACTORS
   - Include: Documented chronic conditions and social/environmental factors.

4. CURRENT DIAGNOSES
   - Include: Primary and clinically significant secondary diagnoses as documented.

5. MEDICATION & ALLERGY SUMMARY
   - Include: All documented medications and allergies with complete details.

6. CLINICAL TIMELINE HIGHLIGHTS
   - Include: Significant events in chronological order as documented (Admission → Changes → Discharge).

7. DIAGNOSTIC FINDINGS (LABS & IMAGING)
   - Include: Critical lab results and imaging findings as documented.

8. THERAPY & FUNCTIONAL STATUS
   - Include: Documented progress in PT/OT/ST and current functional/mobility status.

9. PROCEDURES PERFORMED
   - Include: All documented procedures with dates.

═══════════════════════════════════════════════════════════════════════════════
CRITICAL GUIDELINES
═══════════════════════════════════════════════════════════════════════════════
- NO Interpretation, NO recommendations, NO medical necessity language.
- MANDATORY: Report every clinical detail provided in the extraction data.
- If data is missing for a section, state "Not explicitly documented in available records".
- Use phrases like "Per documentation...", "Records indicate...", "Documented as..." to emphasize source-bound reporting.
- Mandatory Footer: 'This summary is informational only and does not constitute a utilization management decision. Summary based on extracted data which may be incomplete.'
"""
        
        prompt.template = new_template
        prompt.updated_at = datetime.now(timezone.utc)
        
        db.commit()
        
        # Refresh prompt cache
        try:
            from app.services.prompt_service import prompt_service
            prompt_service.refresh_cache()
            print("✓ Prompt cache refreshed")
        except Exception as e:
            print(f"⚠️  Warning: Could not refresh prompt cache: {e}")
        
        print("✅ Successfully updated summary_generation prompt")
        print("\nChanges:")
        print("  - Removed 'DO NOT OMIT ANY INFORMATION' pressure")
        print("  - Changed 'INCLUDE ALL' to 'report all documented'")
        print("  - Added GROUNDING RULES section")
        print("  - Emphasized 'documented' and source-bound language")
        print("  - Added acknowledgment that extraction may be incomplete")
        
    except Exception as e:
        db.rollback()
        print(f"❌ Error: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    print("=" * 80)
    print("Updating Summary Prompt with Grounding Instructions")
    print("=" * 80)
    print()
    update_summary_prompt()
    print()
    print("Done! Summary prompt now emphasizes documentation over completeness.")
