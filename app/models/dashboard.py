"""Dashboard and facet models for multi-agent orchestration."""

from datetime import datetime
from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import relationship
import enum

from app.db.session import Base


class FacetType(str, enum.Enum):
    CASE_OVERVIEW = "case_overview"
    SUMMARY = "summary"
    CLINICAL = "clinical"
    TIMELINE = "timeline"
    RED_FLAGS = "red_flags"
    CONTRADICTIONS = "contradictions"


class FacetStatus(str, enum.Enum):
    PENDING = "pending"
    READY = "ready"
    FAILED = "failed"


class DashboardSnapshot(Base):
    """Represents a versioned snapshot of dashboard data for a case."""

    __tablename__ = "dashboard_snapshots"

    id = Column(String, primary_key=True, index=True)
    case_id = Column(String, ForeignKey("cases.id"), nullable=False, index=True)
    case_version_id = Column(
        String, ForeignKey("case_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    version = Column(Integer, nullable=False, default=1)
    # Store enum as varchar to avoid PostgreSQL enum value mismatches
    status = Column(
        Enum(FacetStatus, native_enum=False, length=20),
        default=FacetStatus.PENDING,
        nullable=False,
    )
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Performance indexes
    __table_args__ = (
        Index('idx_snapshot_case_user', 'case_id', 'user_id'),
        Index('idx_snapshot_version_user', 'case_version_id', 'user_id'),
        Index('idx_snapshot_case_created', 'case_id', 'created_at'),
    )

    facets = relationship(
        "FacetResult",
        back_populates="snapshot",
        cascade="all, delete-orphan",
        order_by="FacetResult.created_at",
    )


class FacetResult(Base):
    """Stores the output for an individual facet."""

    __tablename__ = "facet_results"

    id = Column(String, primary_key=True, index=True)
    snapshot_id = Column(String, ForeignKey("dashboard_snapshots.id"), nullable=False)
    case_id = Column(String, ForeignKey("cases.id"), nullable=False, index=True)
    case_version_id = Column(
        String, ForeignKey("case_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    facet_type = Column(
        Enum(FacetType, native_enum=False, length=50),
        nullable=False
    )
    # Store enum as varchar to avoid PostgreSQL enum value mismatches
    status = Column(
        Enum(FacetStatus, native_enum=False, length=20),
        default=FacetStatus.PENDING,
        nullable=False,
    )
    content = Column(JSON, nullable=True)
    sources = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Performance indexes
    __table_args__ = (
        Index('idx_facet_snapshot_type', 'snapshot_id', 'facet_type'),  # For facet lookups
    )

    snapshot = relationship("DashboardSnapshot", back_populates="facets")
    source_links = relationship(
        "SourceLink",
        back_populates="facet",
        cascade="all, delete-orphan",
        order_by="SourceLink.created_at",
    )


class SourceLink(Base):
    """Normalized linkage between a facet item and its source file/page."""

    __tablename__ = "source_links"

    id = Column(String, primary_key=True, index=True)
    case_id = Column(String, ForeignKey("cases.id"), nullable=False, index=True)
    case_version_id = Column(
        String, ForeignKey("case_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    facet_id = Column(String, ForeignKey("facet_results.id"), nullable=False, index=True)
    item_id = Column(String, nullable=False)
    file_id = Column(String, nullable=True)
    file_name = Column(String, nullable=True)
    page_number = Column(Integer, nullable=True)
    snippet = Column(Text, nullable=True)
    full_text = Column(Text, nullable=True)
    chunk_id = Column(String, nullable=True, index=True)  # Reference to DocumentChunk for RAG
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    facet = relationship("FacetResult", back_populates="source_links")


