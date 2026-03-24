"""Clinical extraction model"""

from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, JSON, Text, Index
from sqlalchemy.orm import relationship

from app.db.session import Base


class ClinicalExtraction(Base):
    """Clinical extraction model"""

    __tablename__ = "clinical_extractions"

    id = Column(String, primary_key=True, index=True)
    case_id = Column(String, ForeignKey("cases.id"), nullable=False, index=True)
    case_version_id = Column(
        String, ForeignKey("case_versions.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
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

    # Version continuity: prior-version excerpts + new doc names for summary prompts (incremental versions)
    version_merge_context = Column(JSON, nullable=True)

    # Phase 2: new-doc metadata + merged base+delta clinical view for summaries / impact
    version_delta_context = Column(JSON, nullable=True)
    merged_clinical_state = Column(JSON, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Performance indexes
    __table_args__ = (
        Index('idx_extraction_case_user', 'case_id', 'user_id'),
        Index('idx_extraction_case_version_user', 'case_version_id', 'user_id'),
    )

    # Relationships
    case = relationship("Case", back_populates="extractions")
    case_version = relationship("CaseVersion", back_populates="clinical_extraction", uselist=False)

    def __repr__(self):
        return f"<ClinicalExtraction for Case {self.case_id}>"

