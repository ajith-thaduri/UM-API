#!/usr/bin/env python3
"""
Script to directly reset a user's password in the database.
Usage: python scripts/reset_password_direct.py <email> <new_password>
"""

import sys
import os

# Add parent directory to path to import app modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.services.auth_service import get_password_hash
from app.db.session import SessionLocal
from app.models.user import User


def reset_password(email: str, new_password: str):
    """Reset password for a user"""
    db = SessionLocal()
    try:
        # Find user by email
        user = db.query(User).filter(User.email == email).first()
        
        if not user:
            print(f"❌ Error: User with email '{email}' not found!")
            return False
        
        # Generate new password hash
        hashed_password = get_password_hash(new_password)
        
        # Update password
        user.hashed_password = hashed_password
        db.commit()
        
        print(f"✅ Successfully reset password for: {email}")
        print(f"   User ID: {user.id}")
        print(f"   User Name: {user.name}")
        print(f"   Role: {user.role}")
        return True
        
    except Exception as e:
        db.rollback()
        print(f"❌ Error updating password: {str(e)}")
        return False
    finally:
        db.close()


def main():
    if len(sys.argv) != 3:
        print("Usage: python scripts/reset_password_direct.py <email> <new_password>")
        print("\nExample:")
        print("  python scripts/reset_password_direct.py naresh.vemparala@brightcone.ai MyNewPassword123")
        sys.exit(1)
    
    email = sys.argv[1]
    new_password = sys.argv[2]
    
    if len(new_password) < 8:
        print("⚠️  Warning: Password should be at least 8 characters long!")
        response = input("Continue anyway? (y/n): ")
        if response.lower() != 'y':
            sys.exit(1)
    
    print(f"\n🔄 Resetting password for: {email}")
    print("="*70)
    
    success = reset_password(email, new_password)
    
    if success:
        print("\n✅ Password reset complete! User can now login with the new password.")
    else:
        print("\n❌ Password reset failed. Please check the error above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
