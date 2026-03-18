"""Upload Session model for storing agentic upload state"""

from datetime import datetime
import uuid
from sqlalchemy import Column, String, Text, DateTime, JSON, Integer, ForeignKey
from app.db.session import Base

class UploadSession(Base):
    """Stores the state of an agentic upload conversation"""
    
    __tablename__ = "upload_sessions"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()), index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    state = Column(String, nullable=False) # ConversationState
    patient_info = Column(JSON, nullable=False) # PatientInfo dict
    case_number = Column(String, nullable=True)
    priority = Column(String, default="normal")
    request_type = Column(String, nullable=True)
    requested_service = Column(Text, nullable=True)
    request_date = Column(String, nullable=True)
    urgency = Column(String, nullable=True)
    
    # Extracted fields
    extracted_request_type = Column(String, nullable=True)
    extracted_diagnosis = Column(Text, nullable=True)
    extracted_request_date = Column(String, nullable=True)
    
    files = Column(JSON, default=list) # List of file info dicts
    messages = Column(JSON, default=list) # List of message dicts
    
    case_id = Column(String, nullable=True) # Linked case after confirmation
    processing_status = Column(String, nullable=True)
    processing_progress = Column(Integer, default=0)
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<UploadSession {self.id} (User: {self.user_id}, State: {self.state})>"
