"""Verify upload_sessions table exists"""
import sys
import os
from sqlalchemy import text

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import SessionLocal

db = SessionLocal()
try:
    result = db.execute(text("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name = 'upload_sessions'
    """)).fetchone()
    
    if result:
        print("✅ SUCCESS: upload_sessions table exists!")
        
        # Check columns
        columns = db.execute(text("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'upload_sessions'
            ORDER BY ordinal_position
        """)).fetchall()
        
        print(f"\n📋 Table has {len(columns)} columns:")
        for col in columns:
            print(f"  - {col[0]}: {col[1]}")
    else:
        print("❌ ERROR: upload_sessions table NOT found!")
        
finally:
    db.close()
