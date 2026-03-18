"""Evidence click tracking model for ROI analytics"""

from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship

from app.db.session import Base


class EvidenceClick(Base):
    """Tracks user interactions with evidence/source documents for ROI analytics"""
    
    __tablename__ = "evidence_clicks"
    
    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    case_id = Column(String, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Entity information
    entity_type = Column(String, nullable=False, index=True)  # "timeline", "medication", "lab", "diagnosis", "chunk"
    entity_id = Column(String, nullable=False)  # Event ID, medication ID, chunk ID, etc.
    
    # Source information
    source_type = Column(String, nullable=False)  # "file" or "chunk"
    file_id = Column(String, nullable=True)  # File ID if source_type is "file"
    page_number = Column(Integer, nullable=True)  # Page number if source_type is "file"
    chunk_id = Column(String, nullable=True)  # Chunk ID if source_type is "chunk"
    
    # Timestamp
    clicked_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    case = relationship("Case", foreign_keys=[case_id])
    
    # Performance indexes for optimized analytics queries
    __table_args__ = (
        Index('idx_click_user_created', 'user_id', 'clicked_at'),  # For user analytics
        Index('idx_click_case_user', 'case_id', 'user_id'),  # For case-specific analytics
    )
    
    def __repr__(self):
        return f"<EvidenceClick {self.id} - {self.entity_type}:{self.entity_id}>"

