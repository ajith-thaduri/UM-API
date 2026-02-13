"""Page temporal profile model for entity-derived temporal reasoning"""

from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, Integer, Index
from sqlalchemy.orm import relationship

from app.db.session import Base


class PageTemporalProfile(Base):
    """
    Derived temporal envelope for pages based on entity dates.
    
    This model captures the temporal range of a page by aggregating
    the dates from all entities found on that page. This enables:
    - Temporal filtering at the page level
    - Timeline queries without LLM inference
    - Contradiction detection via overlapping time ranges
    
    Key Design Principle:
    - Pages inherit time from entities, NEVER the other way around
    - No dates are "invented" - only derived from extracted entities
    - Narrative pages with no dated entities remain temporally neutral
    """
    
    __tablename__ = "page_temporal_profiles"
    
    # Identity
    page_id = Column(String, ForeignKey("normalized_pages.page_id", ondelete="CASCADE"),
                     primary_key=True, index=True)
    
    # Temporal range (derived from entities on this page)
    earliest_entity_date = Column(DateTime, nullable=True, index=True)
    latest_entity_date = Column(DateTime, nullable=True, index=True)
    dated_entity_count = Column(Integer, default=0)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Indexes for temporal queries
    __table_args__ = (
        Index('idx_temporal_range', 'earliest_entity_date', 'latest_entity_date'),
        Index('idx_temporal_earliest', 'earliest_entity_date'),
        Index('idx_temporal_latest', 'latest_entity_date'),
    )
    
    # Relationships
    page = relationship("NormalizedPage", backref="temporal_profile")
    
    def __repr__(self):
        if self.earliest_entity_date and self.latest_entity_date:
            return f"<PageTemporalProfile {self.page_id} ({self.earliest_entity_date.date()} to {self.latest_entity_date.date()})>"
        return f"<PageTemporalProfile {self.page_id} (No temporal data)>"
    
    @property
    def has_temporal_data(self) -> bool:
        """Check if page has any temporal information"""
        return self.dated_entity_count > 0
    
    def contains_date(self, target_date: datetime) -> bool:
        """Check if given date falls within this page's temporal range"""
        if not self.has_temporal_data:
            return False
        return self.earliest_entity_date <= target_date <= self.latest_entity_date
