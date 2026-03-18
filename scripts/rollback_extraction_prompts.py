#!/usr/bin/env python3
"""
Script to rollback extraction prompts to their state before deduplication update.

This script uses the version history system to restore prompts to their previous state.

Usage:
    python scripts/rollback_extraction_prompts.py
"""

import sys
import os
import json

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import SessionLocal
from app.models.prompt import Prompt
from app.repositories.prompt_repository import prompt_repository
from app.repositories.version_history_repository import version_history_repository
from datetime import datetime, timezone

# Prompts to rollback
PROMPTS_TO_ROLLBACK = [
    "meds_allergies_extraction",
    "labs_imaging_vitals_extraction",
    "diagnoses_procedures_extraction",
    "timeline_extraction",
    "therapy_notes_extraction",
    "history_extraction",
]

BACKUP_FILE = "scripts/.prompt_backup.json"


def rollback_from_backup():
    """Rollback prompts using the backup file created during update"""
    
    if not os.path.exists(BACKUP_FILE):
        print(f"✗ Backup file not found: {BACKUP_FILE}")
        print("  Attempting rollback using version history instead...")
        return rollback_from_version_history()
    
    db = SessionLocal()
    rolled_back_count = 0
    
    try:
        # Load backup
        with open(BACKUP_FILE, 'r') as f:
            backup = json.load(f)
        
        print(f"Found backup with {len(backup)} prompts")
        
        for prompt_id, backup_data in backup.items():
            prompt = db.query(Prompt).filter(Prompt.id == prompt_id).first()
            
            if not prompt:
                print(f"⚠ Prompt '{prompt_id}' not found, skipping...")
                continue
            
            # Restore from backup
            result = prompt_repository.update_prompt(
                db=db,
                prompt_id=prompt_id,
                template=prompt.template,  # Keep current template
                system_message=backup_data["system_message"],
                user_id="system",
                change_notes="Rollback: Removed deduplication rules",
                request_id=f"rollback_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
            )
            
            if result:
                print(f"✓ Rolled back '{prompt_id}'")
                rolled_back_count += 1
            else:
                print(f"✗ Failed to rollback '{prompt_id}'")
        
        print(f"\n=== Rollback Summary ===")
        print(f"Rolled back: {rolled_back_count} prompts")
        
    except Exception as e:
        db.rollback()
        print(f"Error: {e}")
        raise
    finally:
        db.close()


def rollback_from_version_history():
    """Rollback prompts using the version history table"""
    
    db = SessionLocal()
    rolled_back_count = 0
    
    try:
        for prompt_id in PROMPTS_TO_ROLLBACK:
            # Get version history for this prompt
            history = prompt_repository.get_prompt_history(db, prompt_id)
            
            if len(history) < 2:
                print(f"⚠ No previous version found for '{prompt_id}', skipping...")
                continue
            
            # Find the version before the deduplication update
            # (second most recent version, since most recent is current)
            target_version = history[1]["version_number"]
            
            result = prompt_repository.rollback_to_version(
                db=db,
                prompt_id=prompt_id,
                version_number=target_version,
                user_id="system",
                request_id=f"rollback_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
            )
            
            if result:
                print(f"✓ Rolled back '{prompt_id}' to version {target_version}")
                rolled_back_count += 1
            else:
                print(f"✗ Failed to rollback '{prompt_id}'")
        
        print(f"\n=== Rollback Summary ===")
        print(f"Rolled back: {rolled_back_count} prompts")
        
    except Exception as e:
        db.rollback()
        print(f"Error: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    print("=== Rolling Back Extraction Prompts ===\n")
    print("This will restore prompts to their state before the deduplication update.\n")
    
    # Confirm with user
    confirm = input("Are you sure you want to rollback? (y/n): ").strip().lower()
    if confirm != 'y':
        print("Rollback cancelled.")
        sys.exit(0)
    
    rollback_from_backup()
    print("\nDone! Restart the backend to apply changes.")
