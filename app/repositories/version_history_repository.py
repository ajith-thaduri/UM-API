"""Version history repository for generic audit trails"""

from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
import uuid
from datetime import datetime, timezone

from app.models.version_history import VersionHistory, VersionEventType


class VersionHistoryRepository:
    """Repository for managing generic version history"""

    def get_next_version_number(self, db: Session, table_name: str, ref_id: str) -> int:
        """
        Get the next version number for a specific record.
        Note: This should be called within a transaction where the target row is locked.
        """
        max_version = db.query(func.max(VersionHistory.version_number)).filter(
            and_(
                VersionHistory.referenceable_table_name == table_name,
                VersionHistory.referenceable_id == ref_id
            )
        ).scalar()
        
        return (max_version or 0) + 1

    def add_entry(
        self, 
        db: Session, 
        table_name: str, 
        ref_id: str, 
        event_type: VersionEventType,
        changes: Optional[Dict[str, Any]] = None,
        snapshot: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
        request_id: Optional[str] = None,
        version_number: Optional[int] = None
    ) -> VersionHistory:
        """Add a new version history entry"""
        if version_number is None:
            version_number = self.get_next_version_number(db, table_name, ref_id)
            
        entry = VersionHistory(
            id=str(uuid.uuid4()),
            referenceable_id=ref_id,
            referenceable_table_name=table_name,
            version_number=version_number,
            event_type=event_type,
            object_changes=changes,
            object_snapshot=snapshot,
            changed_by_user_id=user_id,
            request_id=request_id,
            created_at=datetime.now(timezone.utc)
        )
        db.add(entry)
        return entry

    def get_history(
        self, 
        db: Session, 
        table_name: str, 
        ref_id: str,
        limit: int = 100
    ) -> List[VersionHistory]:
        """Get version history for a specific record"""
        return db.query(VersionHistory).filter(
            and_(
                VersionHistory.referenceable_table_name == table_name,
                VersionHistory.referenceable_id == ref_id
            )
        ).order_by(VersionHistory.version_number.desc()).limit(limit).all()

    def get_version(
        self, 
        db: Session, 
        table_name: str, 
        ref_id: str, 
        version_number: int
    ) -> Optional[VersionHistory]:
        """Get a specific version of a record"""
        return db.query(VersionHistory).filter(
            and_(
                VersionHistory.referenceable_table_name == table_name,
                VersionHistory.referenceable_id == ref_id,
                VersionHistory.version_number == version_number
            )
        ).first()


# Singleton instance
version_history_repository = VersionHistoryRepository()
