#!/usr/bin/env python3
"""
Script to update summary_generation prompt to remove "Potential Missing Info" section.
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import SessionLocal
from app.models.prompt import Prompt
from datetime import datetime, timezone

def update_summary_prompt():
    """Update summary_generation prompt to remove Potential Missing Info section"""
    
    db = SessionLocal()
    try:
        # Get existing prompt
        prompt = db.query(Prompt).filter(Prompt.id == "summary_generation").first()
        if not prompt:
            print("ERROR: summary_generation prompt not found")
            return
        
        print("Updating summary_generation prompt...")
        
        # Updated template without Potential Missing Info section
        prompt.template = """Generate a comprehensive UM-ready clinical summary (1-2 pages) for the following case.

═══════════════════════════════════════════════════════════════════════════════
STEP 1: REVIEW ALL PROVIDED DATA - DO NOT OMIT ANY INFORMATION
═══════════════════════════════════════════════════════════════════════════════

PATIENT: {patient_name}
CASE NUMBER: {case_number}

EXTRACTED CLINICAL DATA (INCLUDE ALL OF THE FOLLOWING):

1. DIAGNOSES ({diagnoses_count} total - INCLUDE ALL):
{diagnoses_str}

2. MEDICATIONS ({meds_count} total - INCLUDE ALL):
{meds_text}

3. ALLERGIES:
{allergies_text}

4. PROCEDURES ({procedures_count} total - INCLUDE ALL):
{procedures_text}

5. LAB RESULTS:
   - Total Labs: {labs_total_count}
   - Abnormal Labs: {labs_abnormal_count}
   - ABNORMAL LAB FINDINGS (INCLUDE ALL):
{labs_text}

6. VITAL SIGNS:
{vitals_text}

7. TIMELINE EVENTS ({timeline_count} total - INCLUDE ALL SIGNIFICANT EVENTS):
{timeline_text}

═══════════════════════════════════════════════════════════════════════════════
STEP 2: CREATE COMPREHENSIVE SUMMARY - COMPLETENESS CHECKLIST
═══════════════════════════════════════════════════════════════════════════════

MANDATORY: Before finalizing, verify you have included:
✓ Primary diagnosis (required)
✓ ONLY 2-3 most significant secondary diagnoses (be selective)
✓ ALL medications with dosages and frequencies
✓ ALL allergies
✓ ALL procedures with dates when available
✓ ONLY critically abnormal or significant lab findings (be selective)
✓ ONLY most significant timeline events (admission, major changes, discharge)
✓ Any other clinically important data

Create a neutral clinical summary with these sections. Each section must include ALL relevant data:

1. PATIENT OVERVIEW
   - Include: Patient name, age (if available), case context
   - Include: Any demographic or identifying information provided

2. CHIEF COMPLAINT & PRESENTATION
   - Include: Primary reason for encounter (as documented)
   - Include: Presenting symptoms or concerns from timeline

3. CURRENT DIAGNOSES
   - Include: Primary diagnosis (required)
   - Include: ONLY 2-3 most clinically significant secondary diagnoses
   - Focus on: Diagnoses that impact current treatment or clinical picture
   - Exclude: Minor/stable chronic conditions unless directly relevant
   - Include: Diagnosis dates if available from timeline
   - Format: List each diagnosis clearly

4. MEDICATION SUMMARY
   - Include: ALL medications with complete details (name, dosage, frequency)
   - Include: Medication start dates if available from timeline
   - Format: List each medication with full prescription details
   - Note: If the same medication appears with different dosages, annotate the previous/lower dose as "(historical)" to indicate dose escalation rather than duplication

5. CLINICAL TIMELINE HIGHLIGHTS
   - Include: Only MOST SIGNIFICANT events in chronological order
   - Focus on: Key clinical milestones, major treatments, and significant changes
   - Be concise: Summarize routine vitals and minor events
   - Prioritize: Admission, procedures, critical changes, discharge

6. KEY LAB/DIAGNOSTIC FINDINGS
   - Include: Only CRITICALLY ABNORMAL or clinically significant lab results
   - Focus on: Labs that influenced treatment decisions
   - Be concise: Group similar findings (e.g., "Multiple elevated liver enzymes")
   - Include: Values and dates only for critical findings

7. PROCEDURES PERFORMED
   - Include: ALL procedures with dates when available
   - Include: Procedure types and any relevant details

═══════════════════════════════════════════════════════════════════════════════
CRITICAL GUIDELINES - COMPLETENESS AND ACCURACY
═══════════════════════════════════════════════════════════════════════════════

COMPLETENESS AND CONCISENESS BALANCE:
- PRIMARY DIAGNOSIS: Include (required)
- SECONDARY DIAGNOSES: Include ONLY 2-3 most clinically significant (not all)
- MEDICATIONS: Include ALL with complete details (these must be complete)
- PROCEDURES: Include ALL documented (these must be complete)
- TIMELINE: Include only significant events (admission, procedures, critical changes, discharge)
- LABS: Include only critically abnormal or clinically significant findings
- Be concise: Summarize routine vitals, minor labs, and repetitive events
- DO NOT skip sections - every section must be populated with available data
- If data is missing, state "Not explicitly documented" rather than omitting the section

ACCURACY REQUIREMENTS:
- Use dates in MM/DD/YYYY format
- Include exact values (lab results, dosages) as provided
- Preserve all clinical terminology and medical terms
- Maintain chronological order for timeline events

NEUTRALITY REQUIREMENTS:
- Be concise, factual, and neutral
- Present information as documented - no interpretation
- NO conclusions, recommendations, or "medical necessity" language
- NO prescriptive statements
- Use neutral phrasing when noting documentation gaps
- Note gaps in documentation using neutral language only

FORMATTING:
- Use clear section headers (all caps)
- Use bullet points for lists
- Maintain professional medical documentation style
- Ensure readability while including all data
- Overall summary should be comprehensive yet readable
- Each section should be detailed but organized
- Prioritize: chief complaint, primary diagnoses, key treatments, significant findings

DO NOT INCLUDE: Any section about "potential missing information" or "items that may require review". Focus only on the documented clinical information."""

        prompt.updated_at = datetime.now(timezone.utc)
        
        db.commit()
        print("✓ Successfully updated summary_generation prompt")
        print("✓ Removed 'Potential Missing Info' section from template")
        
    except Exception as e:
        db.rollback()
        print(f"Error: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    print("=== Updating Summary Generation Prompt ===\n")
    update_summary_prompt()
    print("\nDone!")
