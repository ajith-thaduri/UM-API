import os
import sys

# Add the app directory to sys.path
sys.path.append(os.getcwd())

from app.db.session import SessionLocal
from app.models.user import User

def find_user():
    db = SessionLocal()
    try:
        user = db.query(User).first()
        if user:
            print(f"VALID_USER_ID: {user.id}")
        else:
            print("No users found.")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    find_user()
