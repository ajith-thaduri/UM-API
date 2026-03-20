#!/usr/bin/env python3
"""
Script to generate a password hash for direct database update.
Usage: python scripts/reset_password.py <email> <new_password>
"""

import sys
import hashlib
from passlib.context import CryptContext

# Password hashing context (same as auth_service.py)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def get_password_hash(password: str) -> str:
    """Hash a password using the same method as auth_service.py"""
    # Pre-hash password with SHA-256 to avoid bcrypt 72-byte limit
    password_hash = hashlib.sha256(password.encode("utf-8")).hexdigest()
    return pwd_context.hash(password_hash)


def main():
    if len(sys.argv) != 3:
        print("Usage: python scripts/reset_password.py <email> <new_password>")
        print("\nExample:")
        print("  python scripts/reset_password.py naresh.vemparala@brightcone.ai MyNewPassword123")
        sys.exit(1)
    
    email = sys.argv[1]
    new_password = sys.argv[2]
    
    if len(new_password) < 8:
        print("Warning: Password should be at least 8 characters long!")
        response = input("Continue anyway? (y/n): ")
        if response.lower() != 'y':
            sys.exit(1)
    
    # Generate the password hash
    hashed_password = get_password_hash(new_password)
    
    print("\n" + "="*70)
    print("Password Reset for:", email)
    print("="*70)
    print("\nGenerated Password Hash:")
    print(hashed_password)
    print("\n" + "-"*70)
    print("SQL UPDATE Statement:")
    print("-"*70)
    print(f"""
UPDATE users 
SET hashed_password = '{hashed_password}'
WHERE email = '{email}';
""")
    print("-"*70)
    print("\nTo execute this SQL:")
    print("1. Connect to your PostgreSQL database")
    print("2. Run the UPDATE statement above")
    print("3. Verify with: SELECT email, hashed_password IS NOT NULL FROM users WHERE email = '{email}';")
    print("\n" + "="*70)


if __name__ == "__main__":
    main()
