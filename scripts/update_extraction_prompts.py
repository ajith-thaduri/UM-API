#!/usr/bin/env python3
"""
Script to update extraction prompts with deduplication instructions.
This script adds deduplication guidance to all clinical extraction prompts.

Usage:
    python scripts/update_extraction_prompts.py

Rollback:
    python scripts/rollback_extraction_prompts.py
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timezone
import json

# Deduplication instruction to append to system messages
DEDUPLICATION_INSTRUCTION = """

DEDUPLICATION RULES (CRITICAL):
- Extract each unique clinical entity ONCE per date
- If the same item appears on multiple pages, consolidate into ONE entry
- Choose the entry with the most complete information (dosage, source page, etc.)
- Same medication on same date = ONE entry (even if mentioned multiple times)
- Same lab result on same date = ONE entry (use the value with source reference)
- Always include source_file and source_page for traceability"""

# Prompts to update
PROMPTS_TO_UPDATE = [
    # Batch 1 (Primary Timeline Extractions)
    "meds_allergies_extraction",
    "labs_imaging_vitals_extraction",
    "diagnoses_procedures_extraction",
    "timeline_extraction",
    "therapy_notes_extraction",
    "history_extraction",
    
    # Batch 2 (Component Extractions & Summarization)
    "medications_extraction",
    "labs_extraction",
    "diagnoses_extraction",
    "procedures_extraction",
    "vitals_extraction",
    "imaging_extraction",
    "allergies_extraction",
    "gap_detection",
    "patient_info_extraction",
    "summary_generation",
    "executive_summary_generation",
]

# Store original values for rollback reference
BACKUP_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".prompt_backup.json")


def update_extraction_prompts():
    """Update all extraction prompts with deduplication instructions"""
    
    # Import here to avoid issues when script is run directly
    from app.db.session import SessionLocal
    from app.models.prompt import Prompt
    
    db = SessionLocal()
    updated_count = 0
    skipped_count = 0
    backup = {}
    
    try:
        # First, backup current prompts
        for prompt_id in PROMPTS_TO_UPDATE:
            prompt = db.query(Prompt).filter(Prompt.id == prompt_id).first()
            if prompt:
                backup[prompt_id] = {
                    "system_message": prompt.system_message,
                    "template": prompt.template,
                    "backed_up_at": datetime.now(timezone.utc).isoformat()
                }
        
        # Save backup to file
        with open(BACKUP_FILE, 'w') as f:
            json.dump(backup, f, indent=2)
        print(f"✓ Backed up {len(backup)} prompts to {BACKUP_FILE}")
        
        # Now update each prompt
        for prompt_id in PROMPTS_TO_UPDATE:
            prompt = db.query(Prompt).filter(Prompt.id == prompt_id).first()
            
            if not prompt:
                print(f"⚠ Prompt '{prompt_id}' not found in database, skipping...")
                skipped_count += 1
                continue
            
            # Check if already has deduplication instruction
            if prompt.system_message and "DEDUPLICATION RULES" in prompt.system_message:
                print(f"⚠ Prompt '{prompt_id}' already has deduplication rules, skipping...")
                skipped_count += 1
                continue
            
            # Append deduplication instruction to system message
            current_system_message = prompt.system_message or ""
            prompt.system_message = current_system_message + DEDUPLICATION_INSTRUCTION
            prompt.updated_at = datetime.now(timezone.utc)
            # Note: Not setting updated_by as "system" is not a valid user ID
            
            print(f"✓ Updated '{prompt_id}' with deduplication instructions")
            updated_count += 1
        
        # Commit all changes at once
        db.commit()
        
        print(f"\n=== Summary ===")
        print(f"Updated: {updated_count}")
        print(f"Skipped: {skipped_count}")
        print(f"Backup saved to: {BACKUP_FILE}")
        print(f"\nTo rollback, run: python scripts/rollback_extraction_prompts.py")
        
    except Exception as e:
        db.rollback()
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    print("=== Updating Extraction Prompts with Deduplication Rules ===\n")
    update_extraction_prompts()
    print("\nDone!")
