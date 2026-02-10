"""Conversation model for storing chat history"""

from datetime import datetime
from sqlalchemy import Column, String, Text, DateTime, Integer, JSON, Index
from sqlalchemy.dialects.postgresql import UUID
import uuid

from app.db.session import Base


class ConversationMessage(Base):
    """Stores individual messages in a conversation"""
    
    __tablename__ = "conversation_messages"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()), index=True)
    case_id = Column(String, nullable=False, index=True)  # Case this conversation is about
    user_id = Column(String, nullable=False, index=True)  # User who owns the conversation
    role = Column(String, nullable=False)  # "user" or "assistant"
    content = Column(Text, nullable=False)  # Message content
    sources = Column(JSON, nullable=True)  # List of source references
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Composite index for efficient queries
    __table_args__ = (
        Index('ix_conversation_case_user', 'case_id', 'user_id'),
        Index('ix_conversation_case_created', 'case_id', 'created_at'),
    )
    
    def __repr__(self):
        return f"<ConversationMessage {self.id} - Case {self.case_id}>"


