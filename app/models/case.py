"""Case model"""

from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, DateTime, Enum, ForeignKey, Boolean, Index
from sqlalchemy.orm import relationship
import enum

from app.db.session import Base


class CaseStatus(str, enum.Enum):
    """Case status enumeration"""

    UPLOADED = "uploaded"
    PROCESSING = "processing"
    EXTRACTING = "extracting"
    TIMELINE_BUILDING = "timeline_building"
    READY = "ready"
    REVIEWED = "reviewed"
    FAILED = "failed"


class Priority(str, enum.Enum):
    """Case priority enumeration"""

    URGENT = "urgent"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


class Case(Base):
    """Medical case model"""

    __tablename__ = "cases"

    id = Column(String, primary_key=True, index=True)
    patient_id = Column(String, index=True, nullable=False)
    patient_name = Column(String, nullable=False)
    case_number = Column(String, unique=True, index=True, nullable=False)
    status = Column(
        Enum(CaseStatus, native_enum=False, length=50),
        default=CaseStatus.UPLOADED,
        nullable=False
    )
    priority = Column(
        Enum(Priority, native_enum=False, length=20),
        default=Priority.NORMAL,
        nullable=False
    )
    
    uploaded_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    processed_at = Column(DateTime(timezone=True), nullable=True)
    
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    
    record_count = Column(Integer, default=0)
    page_count = Column(Integer, default=0)  # Calculated from all files
    
    # UM Review tracking
    is_reviewed = Column(Boolean, default=False)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    reviewed_by = Column(String, nullable=True)
    
    # Versioning: live = what end users see by default; processing = in-flight pipeline
    live_version_id = Column(String, ForeignKey("case_versions.id", ondelete="SET NULL"), nullable=True, index=True)
    latest_version_number = Column(Integer, nullable=False, default=1)
    processing_version_id = Column(
        String, ForeignKey("case_versions.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Performance indexes
    __table_args__ = (
        Index('idx_case_user_status', 'user_id', 'status'),
        Index('idx_case_status_created', 'status', 'uploaded_at'),
        Index('idx_case_case_number_user', 'case_number', 'user_id'),
        Index('idx_case_live_version', 'live_version_id'),
    )

    # Relationships
    files = relationship("CaseFile", back_populates="case", order_by="CaseFile.file_order", cascade="all, delete-orphan")
    versions = relationship(
        "CaseVersion",
        back_populates="case",
        foreign_keys="CaseVersion.case_id",
        cascade="all, delete-orphan",
    )
    live_version = relationship("CaseVersion", foreign_keys=[live_version_id], post_update=True)
    processing_version = relationship("CaseVersion", foreign_keys=[processing_version_id], post_update=True)
    # Extractions are per CaseVersion; resolve via live_version or explicit version_id in repositories.
    extractions = relationship("ClinicalExtraction", back_populates="case", foreign_keys="ClinicalExtraction.case_id")
    user = relationship("User", foreign_keys=[user_id])
    decision = relationship("Decision", back_populates="case", uselist=False)
    notes = relationship("CaseNote", back_populates="case", order_by="CaseNote.created_at.desc()")

    def __repr__(self):
        return f"<Case {self.case_number} - {self.status}>"
