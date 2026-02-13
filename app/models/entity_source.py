"""Entity source model for industry-standard source linking"""

from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship, foreign

from app.db.session import Base


class EntitySource(Base):
    """
    Normalized source attribution for extracted entities.
    
    This is the single source of truth for where each entity (medication, lab, timeline event, etc.)
    was found in the source documents. Links entities to document chunks which have accurate
    location data (file_id, page_number, bbox coordinates).
    """
    
    __tablename__ = "entity_sources"
    
    id = Column(String, primary_key=True, index=True)
    case_id = Column(String, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Entity identification
    entity_type = Column(String(50), nullable=False, index=True)  # 'medication', 'lab', 'timeline', 'diagnosis', etc.
    entity_id = Column(String(255), nullable=False, index=True)  # 'medication:0', 'timeline:abc123', 'lab:5', etc. (No FK to entities to allow timeline grounding)
    
    # Source location (from document chunk)
    chunk_id = Column(String, ForeignKey("document_chunks.id", ondelete="SET NULL"), nullable=True, index=True)
    file_id = Column(String, ForeignKey("case_files.id", ondelete="SET NULL"), nullable=True, index=True)
    page_id = Column(String, ForeignKey("normalized_pages.page_id", ondelete="CASCADE"), nullable=True, index=True)
    page_number = Column(Integer, nullable=False)  # Validated page number
    
    # Highlighting data
    bbox = Column(JSONB, nullable=True)  # {x0: float, y0: float, x1: float, y1: float} for precise highlighting
    snippet = Column(Text, nullable=True)  # Exact text from chunk (for text-based highlighting fallback)
    full_text = Column(Text, nullable=True)  # Full page text if available
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    chunk = relationship("DocumentChunk", foreign_keys=[chunk_id])
    file = relationship("CaseFile", foreign_keys=[file_id])
    page = relationship("NormalizedPage", foreign_keys=[page_id])
    entity = relationship("Entity", primaryjoin="foreign(EntitySource.entity_id) == Entity.entity_id", back_populates="sources", overlaps="sources")
    
    def __repr__(self):
        return f"<EntitySource {self.entity_type}:{self.entity_id} -> {self.file_id}:{self.page_number}>"
