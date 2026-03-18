"""Generic version history and audit trail model"""

import enum
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Column, String, Integer, JSON, DateTime, Enum, Index, UniqueConstraint, ForeignKey
from app.db.session import Base


class VersionEventType(str, enum.Enum):
    """Types of version history events"""
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    ROLLBACK = "ROLLBACK"
    DELETE = "DELETE"
    MIGRATED = "MIGRATED"


class VersionHistory(Base):
    """
    Generic version history table for auditing changes to any record.
    """
    __tablename__ = "version_history"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    
    # Polymorphic reference to the target record
    referenceable_id = Column(String, nullable=False)
    referenceable_table_name = Column(String, nullable=False)
    
    version_number = Column(Integer, nullable=False)
    event_type = Column(
        Enum(VersionEventType, native_enum=False, length=20),
        nullable=False
    )
    
    # Changes and state snapshots
    object_changes = Column(JSON, nullable=True)  # e.g. {"template": {"old": "...", "new": "..."}}
    object_snapshot = Column(JSON, nullable=True) # Full record state after change
    
    # Metadata
    changed_by_user_id = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    request_id = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    # Indexes and Constraints
    __table_args__ = (
        UniqueConstraint(
            "referenceable_table_name", 
            "referenceable_id", 
            "version_number", 
            name="uq_version_history_ref_version"
        ),
        Index("ix_version_history_ref", "referenceable_table_name", "referenceable_id"),
        Index(
            "ix_version_history_ref_version_desc", 
            "referenceable_table_name", 
            "referenceable_id", 
            version_number.desc()
        ),
        Index("ix_version_history_created_at_desc", created_at.desc()),
    )

    def __repr__(self):
        return f"<VersionHistory {self.referenceable_table_name}:{self.referenceable_id} V{self.version_number} [{self.event_type}]>"
