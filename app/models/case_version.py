"""Immutable case processing versions (document-set snapshots)."""

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.db.session import Base


def _enum_values(enum_cls):
    """Persist enum .value strings instead of member names."""
    return [member.value for member in enum_cls]


class CaseVersionStatus(str, enum.Enum):
    DRAFT = "draft"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class CaseVersionFileRole(str, enum.Enum):
    """Role of a file within this version snapshot."""

    NEW = "new"  # First appeared in this version
    EXISTING = "existing"  # Carried from base version in an incremental version


class CaseVersion(Base):
    """
    One immutable processing snapshot for a case (v1, v2, ...).
    Live/main pointer is on Case.live_version_id.
    """

    __tablename__ = "case_versions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    case_id = Column(String, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    version_number = Column(Integer, nullable=False)
    status = Column(
        Enum(
            CaseVersionStatus,
            native_enum=False,
            length=20,
            values_callable=_enum_values,
        ),
        default=CaseVersionStatus.DRAFT,
        nullable=False,
    )
    is_live = Column(Boolean, nullable=False, default=False)

    base_version_id = Column(
        String, ForeignKey("case_versions.id", ondelete="SET NULL"), nullable=True, index=True
    )

    change_summary = Column(Text, nullable=True)
    change_reasoning = Column(JSONB, nullable=True)  # structured diff / reasoning (legacy; prefer revision_impact_report)

    # Reviewer-facing version artifacts (populated at finalize for incremental versions)
    revision_impact_report = Column(JSONB, nullable=True)
    confidence_summary = Column(JSONB, nullable=True)
    review_flags = Column(JSONB, nullable=True)
    materiality_label = Column(String(64), nullable=True)

    # Reviewer lineage: base selection, vault picks, upload counts (Phase 2)
    version_processing_metadata = Column(JSONB, nullable=True)

    processing_started_at = Column(DateTime(timezone=True), nullable=True)
    processed_at = Column(DateTime(timezone=True), nullable=True)

    record_count = Column(Integer, default=0)
    page_count = Column(Integer, default=0)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    case = relationship("Case", back_populates="versions", foreign_keys=[case_id])
    base_version = relationship("CaseVersion", remote_side=[id], foreign_keys=[base_version_id])
    # CaseVersionFile also FKs case_versions via inherited_from_version_id — disambiguate membership
    version_files = relationship(
        "CaseVersionFile",
        back_populates="case_version",
        foreign_keys="CaseVersionFile.case_version_id",
        cascade="all, delete-orphan",
        order_by="CaseVersionFile.file_order_within_version",
    )
    clinical_extraction = relationship(
        "ClinicalExtraction",
        back_populates="case_version",
        uselist=False,
    )

    __table_args__ = (
        UniqueConstraint("case_id", "version_number", name="uq_case_versions_case_version_number"),
        Index("idx_case_versions_case_live", "case_id", "is_live"),
    )

    def __repr__(self):
        return f"<CaseVersion {self.case_id} v{self.version_number} {self.status}>"


class CaseVersionFile(Base):
    """Membership of a CaseFile in a specific CaseVersion snapshot."""

    __tablename__ = "case_version_files"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    case_version_id = Column(
        String, ForeignKey("case_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    case_file_id = Column(
        String, ForeignKey("case_files.id", ondelete="CASCADE"), nullable=False, index=True
    )

    file_role = Column(
        Enum(
            CaseVersionFileRole,
            native_enum=False,
            length=20,
            values_callable=_enum_values,
        ),
        nullable=False,
        default=CaseVersionFileRole.NEW,
    )
    inherited_from_version_id = Column(
        String, ForeignKey("case_versions.id", ondelete="SET NULL"), nullable=True
    )
    file_order_within_version = Column(Integer, nullable=False, default=0)

    case_version = relationship(
        "CaseVersion",
        back_populates="version_files",
        foreign_keys=[case_version_id],
    )
    inherited_from_version = relationship(
        "CaseVersion",
        foreign_keys=[inherited_from_version_id],
    )
    case_file = relationship("CaseFile", back_populates="version_memberships")

    __table_args__ = (
        UniqueConstraint("case_version_id", "case_file_id", name="uq_case_version_file_member"),
        Index("idx_case_version_files_version_order", "case_version_id", "file_order_within_version"),
    )
