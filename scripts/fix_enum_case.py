"""Fix enum case mismatch in production database"""
import sys
import os
from sqlalchemy import text

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import SessionLocal

db = SessionLocal()
try:
    print("🔄 Fixing user role enum case mismatch...")
    
    # Update all lowercase roles to uppercase
    updates = [
        ("um_nurse", "UM_NURSE"),
        ("medical_director", "MEDICAL_DIRECTOR"),
        ("admin", "ADMIN"),
        ("auditor", "AUDITOR"),
    ]
    
    total_updated = 0
    for old_val, new_val in updates:
        result = db.execute(text(f"""
            UPDATE users 
            SET role = '{new_val}' 
            WHERE role = '{old_val}'
        """))
        count = result.rowcount
        if count > 0:
            print(f"  ✅ Updated {count} users from '{old_val}' to '{new_val}'")
            total_updated += count
    
    db.commit()
    print(f"\n✨ Fixed {total_updated} user records!")
    
except Exception as e:
    print(f"❌ Error: {e}")
    db.rollback()
finally:
    db.close()
