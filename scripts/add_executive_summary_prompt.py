#!/usr/bin/env python3
"""
Script to add executive_summary_generation prompt to the database.
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import SessionLocal
from app.models.prompt import Prompt
from datetime import datetime, timezone

def add_executive_summary_prompt():
    """Add executive_summary_generation prompt"""
    
    db = SessionLocal()
    try:
        # Check if prompt already exists
        existing = db.query(Prompt).filter(Prompt.id == "executive_summary_generation").first()
        if existing:
            print("Executive summary prompt already exists. Updating...")
            prompt = existing
        else:
            print("Creating new executive summary prompt...")
            prompt = Prompt(id="executive_summary_generation")
        
        # Set prompt properties
        prompt.category = "clinical_summary"
        prompt.name = "Executive Summary Generation"
        prompt.description = "Generates a concise 4-6 bullet point executive summary for PDFs and quick reference"
        
        prompt.system_message = """You are a clinical summary specialist for Utilization Management (UM) reviewers. Your task is to create a comprehensive yet concise executive summary that helps Medical Directors, physicians, and nurses quickly understand the patient's clinical journey.

AUDIENCE: Medical Directors, physicians, nurses, and case managers reviewing cases for health plan authorization.

PURPOSE: Provide a clear, chronological narrative of what happened to the patient - their admission, clinical course, treatment, and outcome.

RULES:
- Write EXACTLY 4-6 bullet points (no more, no less) in chronological narrative style
- Tell the patient's story: admission → clinical course → treatment → outcome
- Each bullet should be a complete clinical statement (can be 2-3 sentences for detail)
- Use MM/DD/YYYY date format
- Be factual and neutral - no interpretation or medical necessity judgments
- Include specific clinical details: dates, values, interventions, response to treatment
- Focus on key clinical decision points and changes in patient status
- No approval/denial recommendations or authorization language"""
        
        prompt.template = """Create a comprehensive executive summary for Medical Directors and clinical reviewers. Tell the patient's clinical story in a clear, chronological narrative.

PATIENT: {patient_name}
CASE NUMBER: {case_number}

CLINICAL DATA AVAILABLE:

ADMISSION/DISCHARGE:
{admission_discharge_info}

PRIMARY DIAGNOSES:
{primary_diagnoses}

KEY MEDICATIONS:
{key_medications}

CRITICAL LAB FINDINGS:
{critical_labs}

SIGNIFICANT EVENTS:
{key_events}

POTENTIAL CONCERNS:
{concerns}

INSTRUCTIONS:
Create EXACTLY 4-6 bullet points that tell the patient's story chronologically. Each bullet should be comprehensive (2-3 sentences) to capture the essential details:

1. PATIENT PRESENTATION (1 bullet):
   • Patient demographics, admission date, presenting complaint, and initial clinical findings

2. CLINICAL COURSE & TREATMENT (2-3 bullets):
   • Working diagnosis with key diagnostic findings (labs, imaging, vitals)
   • Treatment plan initiated (medications with doses, procedures, interventions)
   • Patient's response to treatment, clinical progress, and any complications

3. OUTCOME & DISCHARGE (1-2 bullets):
   • Discharge date, patient status, disposition, and discharge medications
   • Follow-up plan and any clinical considerations or documentation gaps

FORMAT REQUIREMENTS:
- Write EXACTLY 4-6 bullet points (STRICT LIMIT)
- Start each bullet with "•"
- Write 2-3 complete sentences per bullet for comprehensive detail
- Include specific dates, lab values, medication names/doses
- Maintain chronological flow
- Use clear, professional medical language

EXAMPLE EXECUTIVE SUMMARY (6 bullets):
• Patient Evelyn Marie Caldwell with documented history of long-standing hypertensive cardiomyopathy presented with diastolic heart failure (HFpEF) and microvascular angina, though specific admission date and presenting symptoms are not documented in available records. Discharge occurred on 01/30/2026.

• Clinical workup revealed heart failure with preserved ejection fraction (HFpEF) as the primary diagnosis, secondary to chronic hypertensive cardiomyopathy. Patient also diagnosed with microvascular angina, indicating coronary microvascular dysfunction contributing to cardiac symptoms.

• Laboratory findings on admission demonstrated microcytic anemia with hemoglobin 10.9 g/dL, hematocrit 33.4%, MCV 78 fL, and MCH 26.1 pg, suggesting possible iron deficiency anemia or chronic disease anemia. RBC count was 4.05 x10⁶/µL. Thyroid function testing showed elevated TSH at 6.1, indicating subclinical hypothyroidism requiring treatment initiation.

• Comprehensive guideline-directed medical therapy for HFpEF initiated on 01/27/2026 including Sacubitril/Valsartan 49/51 mg BID (ARNI therapy), Carvedilol 12.5 mg BID (beta-blocker), and Spironolactone 25 mg daily (mineralocorticoid receptor antagonist). Additional cardiovascular therapy included Isosorbide mononitrate ER 30 mg daily for management of microvascular angina and afterload reduction. Levothyroxine 25 mcg daily initiated to address subclinical hypothyroidism.

• Patient discharged on 01/30/2026 (3 days after medication initiation on 01/27/2026) with continuation of all five newly initiated medications: Sacubitril/Valsartan, Carvedilol, Spironolactone, Isosorbide mononitrate ER, and Levothyroxine. Patient's clinical response to initiated medical therapy and tolerance of medication regimen during hospitalization is not documented in available records.

• Clinical considerations: Significant documentation gaps exist regarding admission date, presenting symptoms, clinical course details, vital signs, additional diagnostic studies (echocardiogram findings, EKG results), and patient's functional status at discharge. Patient requires close outpatient follow-up for titration of HFpEF medications (particularly Sacubitril/Valsartan and Carvedilol which are typically started at lower doses), monitoring of renal function and potassium with ARNI and Spironolactone therapy, and repeat thyroid function testing in 6-8 weeks.

Return ONLY the bullet points, no headers or additional text."""

        prompt.variables = [
            "patient_name",
            "case_number",
            "admission_discharge_info",
            "primary_diagnoses",
            "key_medications",
            "critical_labs",
            "key_events",
            "concerns"
        ]
        
        prompt.is_active = True
        prompt.updated_at = datetime.now(timezone.utc)
        
        if not existing:
            db.add(prompt)
        
        db.commit()
        print(f"✓ Successfully {'updated' if existing else 'created'} executive_summary_generation prompt")
        
    except Exception as e:
        db.rollback()
        print(f"Error: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    print("=== Adding Executive Summary Prompt ===\n")
    add_executive_summary_prompt()
    print("\nDone!")
