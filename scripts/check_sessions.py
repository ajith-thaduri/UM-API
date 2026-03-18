"""Check the contents of the last few upload sessions"""
import sys
import os
import json

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import SessionLocal
from app.models.upload_session import UploadSession
from sqlalchemy import desc

db = SessionLocal()
try:
    sessions = db.query(UploadSession).order_by(desc(UploadSession.updated_at)).limit(5).all()
    
    print(f"🔍 Found {len(sessions)} recent sessions:\n")
    
    for s in sessions:
        print(f"Session ID: {s.id}")
        print(f"  User ID: {s.user_id}")
        print(f"  State: {s.state}")
        print(f"  Patient Info: {json.dumps(s.patient_info, indent=2)}")
        print(f"  Case Number: {s.case_number}")
        print(f"  Priority: {s.priority}")
        print(f"  Updated At: {s.updated_at}")
        
        # Check if case number exists in cases table
        if s.case_number:
            from app.models.case import Case
            exists = db.query(Case).filter(Case.case_number == s.case_number, Case.user_id == s.user_id).first()
            if exists:
                print(f"  ⚠️ ALERT: Case number {s.case_number} already exists in cases table!")
        
        print("-" * 40)
        
finally:
    db.close()
