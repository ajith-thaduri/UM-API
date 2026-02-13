"""Entity model - atomic truth with temporal anchor"""

from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, Integer, Float, Text, Index
from sqlalchemy.orm import relationship, foreign
from sqlalchemy.dialects.postgresql import JSONB

from app.db.session import Base


class Entity(Base):
    """
    First-class entity model representing extracted clinical facts.
    
    This is the atomic unit of truth in the Page-Indexed RAG system.
    Each entity is grounded to a specific page via EntitySource.
    """
    
    __tablename__ = "entities"
    
    # Identity
    entity_id = Column(String, primary_key=True, index=True)
    case_id = Column(String, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Type and value
    entity_type = Column(String(50), nullable=False, index=True)  # medication, lab, diagnosis, etc.
    value = Column(Text, nullable=False)  # Raw value (e.g. "Lasix 40mg")
    normalized_value = Column(Text, nullable=True, index=True)  # Standardized (e.g., "Furosemide")
    
    # Temporal anchor (CRITICAL)
    # The date associated with this specific entity instance
    entity_date = Column(DateTime, nullable=True, index=True)
    
    # Confidence and metadata
    confidence = Column(Float, default=1.0)
    entity_metadata = Column(JSONB, nullable=True)  # Renamed from metadata to avoid SQLAlchemy conflict
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Indexes
    __table_args__ = (
        Index('idx_entity_type_date', 'entity_type', 'entity_date'),
        Index('idx_entity_normalized_value', 'normalized_value'),
        Index('idx_entity_case_type', 'case_id', 'entity_type'),
    )
    
    # Relationships
    case = relationship("Case", backref="entities")
    sources = relationship("EntitySource", primaryjoin="Entity.entity_id == foreign(EntitySource.entity_id)", back_populates="entity", cascade="all, delete-orphan", overlaps="entity,sources")
    # pages relationship via sources
    
    def __repr__(self):
        date_str = self.entity_date.strftime('%Y-%m-%d') if self.entity_date else "No Date"
        return f"<Entity {self.entity_type}: {self.value} ({date_str})>"
