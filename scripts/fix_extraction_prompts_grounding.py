#!/usr/bin/env python3
"""
Script to update extraction prompts with grounding-focused instructions.
Removes "Extract ALL" pressure and adds explicit source grounding rules.
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import SessionLocal
from app.models.prompt import Prompt
from datetime import datetime, timezone

def update_extraction_prompts():
    """Update extraction prompts with grounding-focused system messages"""
    
    db = SessionLocal()
    try:
        # Target prompts to update
        target_prompts = [
            "meds_allergies_extraction",
            "labs_imaging_vitals_extraction",
            "diagnoses_procedures_extraction"
        ]
        
        # New grounding-focused system message
        new_system_message = """You are a clinical data extraction specialist focused on ACCURACY and SOURCE GROUNDING.

CRITICAL RULES:
1. Extract ONLY information explicitly present in the provided context
2. If information is not in the context, return null/empty - DO NOT INFER OR FABRICATE
3. Report what is documented, not what should be documented
4. Quality over quantity - accurate entries only
5. Always include source_file and source_page for traceability

FORBIDDEN BEHAVIORS:
- Fabricating data to "complete" the record
- Inferring values not explicitly stated
- Creating specific dates when only ranges are given
- Assuming medication changes without documentation
- Inventing lab values or vital signs
- Guessing dosages, frequencies, or clinical values

VERIFICATION PRINCIPLE:
When uncertain: OMIT the field rather than guess. It is better to return incomplete but accurate data than complete but fabricated data.

DEDUPLICATION RULES (CRITICAL):
- Extract each unique clinical entity ONCE per date
- If the same item appears on multiple pages, consolidate into ONE entry
- Choose the entry with the most complete information (dosage, source page, etc.)
- Same medication on same date = ONE entry (even if mentioned multiple times)
- Same lab result on same date = ONE entry (use the value with source reference)
- Always include source_file and source_page for traceability"""

        updated_count = 0
        
        for prompt_id in target_prompts:
            prompt = db.query(Prompt).filter(Prompt.id == prompt_id).first()
            
            if not prompt:
                print(f"⚠️  Prompt '{prompt_id}' not found, skipping")
                continue
            
            # Backup old system message
            old_system_message = prompt.system_message
            
            # Update system message
            prompt.system_message = new_system_message
            prompt.updated_at = datetime.now(timezone.utc)
            
            updated_count += 1
            print(f"✓ Updated '{prompt_id}' with grounding-focused system message")
        
        db.commit()
        
        # Refresh prompt cache
        try:
            from app.services.prompt_service import prompt_service
            prompt_service.refresh_cache()
            print("✓ Prompt cache refreshed")
        except Exception as e:
            print(f"⚠️  Warning: Could not refresh prompt cache: {e}")
        
        print(f"\n✅ Successfully updated {updated_count} extraction prompts")
        print("\nChanges:")
        print("  - Removed 'Extract ALL' pressure language")
        print("  - Added explicit grounding instructions")
        print("  - Added forbidden behaviors list")
        print("  - Emphasized accuracy over completeness")
        
    except Exception as e:
        db.rollback()
        print(f"❌ Error updating prompts: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    print("=" * 80)
    print("Updating Extraction Prompts with Grounding Instructions")
    print("=" * 80)
    print()
    update_extraction_prompts()
    print()
    print("Done! Extraction prompts now emphasize source grounding over completeness.")
