import os
import sys

# Add the app directory to sys.path
sys.path.append(os.getcwd())

from app.db.session import SessionLocal
from app.repositories.prompt_repository import prompt_repository

def fetch_prompts():
    db = SessionLocal()
    try:
        prompt_ids = ["summary_generation", "executive_summary_generation"]
        for p_id in prompt_ids:
            print(f"\n--- PROMPT: {p_id} ---")
            p = prompt_repository.get_by_id(db, p_id)
            if p:
                print(f"SYSTEM MESSAGE:\n{p.system_message}\n")
                print(f"TEMPLATE:\n{p.template}\n")
            else:
                print(f"Prompt {p_id} NOT FOUND")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    fetch_prompts()
