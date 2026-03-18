
import asyncio
import os
import sys

# Add the project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db.session import SessionLocal
from app.models.case import Case
from app.models.user import User

async def get_ids():
    db = SessionLocal()
    try:
        case = db.query(Case).first()
        user = db.query(User).first()
        if case and user:
            print(f"CASE_ID={case.id}")
            print(f"USER_ID={user.id}")
        else:
            print("No case or user found")
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(get_ids())
