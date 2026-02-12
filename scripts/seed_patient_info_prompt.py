
import sys
import os
import json
from datetime import datetime

# Add parent directory to path so we can import app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import SessionLocal
from app.models.prompt import Prompt

def seed_prompt():
    db = SessionLocal()
    
    prompt_id = "patient_info_extraction"
    
    # Check if prompt already exists
    existing = db.query(Prompt).filter(Prompt.id == prompt_id).first()
    if existing:
        print(f"Prompt '{prompt_id}' already exists. Skipping.")
        db.close()
        return

    print(f"Seeding prompt '{prompt_id}'...")
    
    template = """
Please extract the following information from the text below.

TEXT:
{text}

REQUIRED FIELDS:
- name: Patient's full name (format: "First Last")
- dob: Date of birth (MM/DD/YYYY)
- mrn: Medical Record Number
- gender: Male/Female
- encounter_date: Date of the visit/encounter (MM/DD/YYYY)
- provider: Attending provider name
- facility: Name of the facility
- request_type: Type of request (Inpatient, Outpatient, DME, Pharmacy, etc.)
- diagnosis: Primary diagnosis or reason for visit
- request_date: Date of the request (if applicable)
- urgency: Routine, Expedited, or Urgent
- is_medical_record: Boolean (true if this is a medical document)
- document_type: Type of document (e.g., medical_record, lab_report, imaging, discharge)
- relevance_reason: Brief explanation of why this document is relevant or irrelevant

INSTRUCTIONS:
1. Extract ALL fields you can find.
2. If a field is not found, use null or omit it.
3. Normalize all dates to MM/DD/YYYY.
4. Normalize gender to "Male" or "Female".
5. For request_type, infer from context if not explicit.
6. Provide output as a SINGLE JSON object.
"""

    system_message = """You are an expert medical data extractor. Your job is to extract structured patient demographics and case context from raw medical text.
You MUST extract the data in a valid JSON format."""

    new_prompt = Prompt(
        id=prompt_id,
        category="extraction",
        name="Patient Info Extraction",
        description="Extract patient demographics and case context from uploaded files",
        template=template,
        system_message=system_message,
        variables=["text"],
        is_active=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    
    db.add(new_prompt)
    db.commit()
    print(f"Successfully seeded prompt '{prompt_id}'!")
    db.close()

if __name__ == "__main__":
    seed_prompt()
