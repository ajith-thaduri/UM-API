"""Clinical extraction model"""

from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, JSON, Text, Index
from sqlalchemy.orm import relationship

from app.db.session import Base


class ClinicalExtraction(Base):
    """Clinical extraction model"""

    __tablename__ = "clinical_extractions"

    id = Column(String, primary_key=True, index=True)
    case_id = Column(String, ForeignKey("cases.id"), unique=True, nullable=False)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Extracted data stored as JSON
    extracted_data = Column(JSON, nullable=True)
    timeline = Column(JSON, nullable=True)  # Detailed timeline with all events
    timeline_summary = Column(JSON, nullable=True)  # Summary timeline with major events only
    contradictions = Column(JSON, nullable=True)
    
    # Summary text
    summary = Column(Text, nullable=True)
    executive_summary = Column(Text, nullable=True)  # Concise 5-10 bullet point summary for PDFs
    
    # Track edited sections
    edited_sections = Column(JSON, nullable=True)  # {"section_name": {"content": "...", "edited_by": "...", "edited_at": "..."}}
    
    # Source document mapping for evidence linking
    source_mapping = Column(JSON, nullable=True)  # {"file_page_mapping": {...}, "files": [...]}
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Performance indexes
    __table_args__ = (
        Index('idx_extraction_case_user', 'case_id', 'user_id'),  # Composite for user-scoped queries
    )
    
    # Relationships
    case = relationship("Case", back_populates="extraction")

    def __repr__(self):
        return f"<ClinicalExtraction for Case {self.case_id}>"

