#!/usr/bin/env python3
"""
Script to view the current summary_generation prompt from the database.
"""
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import SessionLocal
from app.models.prompt import Prompt

def view_summary_prompt():
    """View the summary_generation prompt"""
    db = SessionLocal()
    try:
        # First, list all prompts
        all_prompts = db.query(Prompt).all()
        print(f"\n📋 Found {len(all_prompts)} prompts in database:")
        for p in all_prompts:
            print(f"  - {p.name} (active: {p.is_active})")
        
        # Find the Summary Generation prompt (case-sensitive)
        prompt = db.query(Prompt).filter(Prompt.name == "Summary Generation").first()
        
        if not prompt:
            print("\n❌ Summary Generation prompt not found in database")
            return
        
        print("=" * 80)
        print("📋 SUMMARY GENERATION PROMPT")
        print("=" * 80)
        print(f"\n🔹 Name: {prompt.name}")
        print(f"🔹 Description: {prompt.description}")
        print(f"🔹 Model: {prompt.model if hasattr(prompt, 'model') else 'N/A'}")
        print(f"🔹 Active: {prompt.is_active}")
        
        print("\n" + "=" * 80)
        print("📝 SYSTEM MESSAGE")
        print("=" * 80)
        print(prompt.system_message)
        
        print("\n" + "=" * 80)
        print("📄 TEMPLATE")
        print("=" * 80)
        print(prompt.template)
        
        print("\n" + "=" * 80)
        print("✅ Prompt retrieved successfully")
        print("=" * 80)
        
    finally:
        db.close()

if __name__ == "__main__":
    view_summary_prompt()
