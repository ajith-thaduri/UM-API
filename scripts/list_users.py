"""List all users in the database"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import SessionLocal
from app.models.user import User

db = SessionLocal()
try:
    users = db.query(User).all()
    print(f"\nFound {len(users)} users:\n")
    for user in users:
        print(f"  Email: {user.email}")
        print(f"  Name: {user.name}")
        print(f"  ID: {user.id}")
        print(f"  Role: {user.role}")
        print()
finally:
    db.close()

