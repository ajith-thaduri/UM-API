ailed to load resource: the server responded with a status of 400 (Bad Request)Understand this error
intercept-console-error.ts:42 Failed to confirm upload: Error: HTTP error! status: 400
    at ApiService.request (api.ts:85:15)"""Test the upload agent message endpoint directly"""
import sys
import os
import json

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import SessionLocal
from app.services.upload_agent_service import upload_agent_service
from app.models.user import User
from sqlalchemy import text

db = SessionLocal()
try:
    # Get a test user
    user = db.query(User).first()
    if not user:
        print("❌ No users found in database. Please create a user first.")
        exit(1)
    
    print(f"✅ Found user: {user.email}")
    
    # Create a test session
    print("\n🔄 Creating test upload session...")
    session_id, greeting = upload_agent_service.start_session(db, user.id)
    print(f"✅ Session created: {session_id}")
    
    # Simulate sending "Yes, looks good" message
    print("\n🔄 Simulating 'Yes, looks good' message...")
    try:
        import asyncio
        response = asyncio.run(upload_agent_service.process_message(
            db=db,
            session_id=session_id,
            user_message="Yes, looks good"
        ))
        print(f"✅ SUCCESS! Response: {json.dumps(response.to_dict(), indent=2)}")
    except Exception as e:
        print(f"❌ ERROR processing message: {e}")
        import traceback
        traceback.print_exc()
        
finally:
    db.close()
