"""Repository for entity sources."""
from typing import List, Optional
from sqlalchemy.orm import Session

from app.repositories.base import BaseRepository
from app.models.entity_source import EntitySource


class EntitySourceRepository(BaseRepository[EntitySource]):
    def __init__(self):
        super().__init__(EntitySource)
    
    def get_by_entity(
        self, 
        db: Session, 
        case_id: str, 
        entity_type: str, 
        entity_id: str,
        user_id: Optional[str] = None
    ) -> Optional[EntitySource]:
        """Get source for a specific entity."""
        query = db.query(EntitySource).filter(
            EntitySource.case_id == case_id,
            EntitySource.entity_type == entity_type,
            EntitySource.entity_id == entity_id
        )
        if user_id:
            query = query.filter(EntitySource.user_id == user_id)
        return query.first()
    
    def list_for_case(
        self,
        db: Session,
        case_id: str,
        user_id: Optional[str] = None,
        entity_type: Optional[str] = None,
        case_version_id: Optional[str] = None,
    ) -> List[EntitySource]:
        """List entity sources for a case, optionally scoped to a processing version."""
        query = db.query(EntitySource).filter(EntitySource.case_id == case_id)
        if case_version_id:
            query = query.filter(EntitySource.case_version_id == case_version_id)
        if user_id:
            query = query.filter(EntitySource.user_id == user_id)
        if entity_type:
            query = query.filter(EntitySource.entity_type == entity_type)
        return query.order_by(EntitySource.created_at.desc()).all()
    
    def list_for_chunk(self, db: Session, chunk_id: str) -> List[EntitySource]:
        """List all entities that reference a specific chunk."""
        return (
            db.query(EntitySource)
            .filter(EntitySource.chunk_id == chunk_id)
            .order_by(EntitySource.created_at.desc())
            .all()
        )
    
    def delete_for_case(self, db: Session, case_id: str, user_id: Optional[str] = None) -> int:
        """Delete all entity sources for a case (used when reprocessing)."""
        query = db.query(EntitySource).filter(EntitySource.case_id == case_id)
        if user_id:
            query = query.filter(EntitySource.user_id == user_id)
        count = query.count()
        query.delete(synchronize_session=False)
        return count

