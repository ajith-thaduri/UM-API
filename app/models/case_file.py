"""Case file model"""

from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship

from app.db.session import Base


class CaseFile(Base):
    """Case file model for tracking multiple files per case"""

    __tablename__ = "case_files"

    id = Column(String, primary_key=True, index=True)
    case_id = Column(String, ForeignKey("cases.id"), nullable=False, index=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    
    file_name = Column(String, nullable=False)  # Original filename
    file_path = Column(String, nullable=False)  # Storage path
    file_size = Column(Integer, nullable=False)  # File size in bytes
    page_count = Column(Integer, default=0)  # Number of pages
    
    file_order = Column(Integer, default=0)  # Order of upload (for display)
    
    document_type = Column(String(length=50), nullable=True)  # Detected document type (e.g., social_work, case_management, medical_record, etc.)

    introduced_in_case_version_id = Column(
        String, ForeignKey("case_versions.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Last case version snapshot that included this file (reviewer vault / lineage)
    latest_used_in_case_version_id = Column(
        String, ForeignKey("case_versions.id", ondelete="SET NULL"), nullable=True, index=True
    )

    uploaded_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Performance indexes
    __table_args__ = (
        Index('idx_case_file_case_order', 'case_id', 'file_order'),  # For ordered file loading
    )
    
    # Relationships
    case = relationship("Case", back_populates="files")
    introduced_in_version = relationship("CaseVersion", foreign_keys=[introduced_in_case_version_id])
    latest_used_in_version = relationship(
        "CaseVersion", foreign_keys=[latest_used_in_case_version_id]
    )
    version_memberships = relationship("CaseVersionFile", back_populates="case_file", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<CaseFile {self.file_name} - Case {self.case_id}>"








