"""Page vector model for page-level embeddings"""

from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, Integer, Index
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector

from app.db.session import Base


class PageVector(Base):
    """
    Page-level embeddings for relevance gating in page-indexed RAG.
    
    Each page gets one embedding representing the entire page's meaning.
    This is used to reduce retrieval scope from 1,500 pages → 20 most relevant pages
    before chunk-level retrieval.
    
    Key Design:
    - Page embeddings are for GATING, not precision
    - Chunks are retrieved ONLY from selected pages
    - This prevents retrieval explosion at scale
    """
    
    __tablename__ = "page_vectors"
    
    # Identity
    page_id = Column(String, ForeignKey("normalized_pages.page_id", ondelete="CASCADE"), 
                     primary_key=True, index=True)
    case_id = Column(String, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Embedding (entire page meaning)
    # 1536 dimensions for OpenAI text-embedding-3-small
    embedding = Column(Vector(1536), nullable=False)
    
    # Entity density metadata (for ranking)
    entity_count = Column(Integer, default=0)  # Total entities on page
    dated_entity_count = Column(Integer, default=0)  # Entities with temporal anchors
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Vector index for efficient similarity search
    __table_args__ = (
        Index('idx_page_embedding_cosine', 'embedding',
              postgresql_using='hnsw',
              postgresql_with={'m': 16, 'ef_construction': 64},
              postgresql_ops={'embedding': 'vector_cosine_ops'}),
        Index('idx_page_vectors_case_user', 'case_id', 'user_id'),
    )
    
    # Relationships
    page = relationship("NormalizedPage", backref="vector")
    
    def __repr__(self):
        return f"<PageVector {self.page_id} (Entities: {self.entity_count}, Dated: {self.dated_entity_count})>"
