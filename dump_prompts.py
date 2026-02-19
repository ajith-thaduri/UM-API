import os
import sys

# Add the app directory to sys.path
sys.path.append(os.getcwd())

from app.db.session import SessionLocal
from app.repositories.prompt_repository import prompt_repository

def dump_prompts():
    db = SessionLocal()
    try:
        all_prompts = db.query(prompt_repository.model).all()
        for p in all_prompts:
            with open(f"prompt_{p.id}.txt", "w") as f:
                f.write(f"PROMPT_ID: {p.id}\n")
                f.write(f"SYSTEM_MESSAGE:\n{p.system_message}\n")
                f.write(f"TEMPLATE:\n{p.template}\n")
            print(f"Dumped {p.id} to prompt_{p.id}.txt")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    dump_prompts()
