import asyncio
import uuid
from unittest.mock import MagicMock
from app.services.upload_agent_service import upload_agent_service, AnalysisResult
from app.services.pdf_analyzer_service import FileAnalysis, PatientInfo
# from app.core.database import SessionLocal  # Removed, using mock

# Mock DB Session
class MockSession:
    def __init__(self):
        self.store = {}
    
    def add(self, obj):
        if not obj.id:
            obj.id = str(uuid.uuid4())
        self.store[obj.id] = obj
        
    def commit(self):
        pass
        
    def query(self, model):
        return self
        
    def filter(self, *args):
        return self
        
    def first(self):
        return None

# Mock Repository - monkey patch for simplicity
original_repo = upload_agent_service.repository
mock_store = {}

class MockRepo:
    def create(self, db, session):
        mock_store[session.id] = session
        return session
    
    def get_by_id(self, db, session_id):
        return mock_store.get(session_id)
    
    def update(self, db, session):
        mock_store[session.id] = session
        return session

upload_agent_service.repository = MockRepo()

async def simulate_conversation():
    print("--- Starting Simulation ---")
    db = MagicMock() # Use MagicMock for DB session just to pass type checks if any
    
    # 1. Start Session
    session_id, greeting = upload_agent_service.start_session(db)
    print(f"Agent: {greeting.message}")
    
    # 2. Upload "Files" (Simulate analysis result)
    print("\n[User uploads file]")
    analysis = AnalysisResult(
        patient_info=PatientInfo(
            name="John Doe",
            dob="01/01/1980"
            # Missing MRN, Case Number, etc.
        ),
        files=[FileAnalysis(
            file_name="test_record.pdf",
            file_path="/tmp/test.pdf",
            page_count=5,
            file_size=1024,
            extraction_preview="Patient Name: John Doe DOB: 01/01/1980",
            detected_type="medical_record",
            confidence=0.9
        )],
        total_pages=5,
        extraction_confidence=0.8,
        raw_text_preview="Patient Name: John Doe DOB: 01/01/1980"
    )
    
    response = await upload_agent_service.handle_files_uploaded(db, session_id, analysis)
    print(f"Agent: {response.message} (Data: {response.extracted_data})")
    
    # 3. Simulate User Confirmation
    user_msg = "Yes, looks good"
    print(f"\nUser: {user_msg}")
    response = await upload_agent_service.process_message(db, session_id, user_msg)
    print(f"Agent: {response.message}")
    
    # 4. Simulate User Response 2 (Providing MRN)
    user_msg = "The MRN is 123456789"
    print(f"\nUser: {user_msg}")
    response = await upload_agent_service.process_message(db, session_id, user_msg)
    print(f"Agent: {response.message}")
    
    # 5. Simulate User Response 3 (Providing Case details non-linearly)
    user_msg = "This is an urgent request for specific Inpatient services. Request date is today."
    print(f"\nUser: {user_msg}")
    response = await upload_agent_service.process_message(db, session_id, user_msg)
    print(f"Agent: {response.message}")

if __name__ == "__main__":
    asyncio.run(simulate_conversation())
