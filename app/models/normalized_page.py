"""Normalized page model - first-class page abstraction for page-indexed RAG"""

import hashlib
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, Integer, Text, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.db.session import Base


class NormalizedPage(Base):
    """
    First-class page model - immutable source of truth for document pages.
    
    Each page represents a single page from a PDF document with:
    - Raw text content
    - Layout preservation (bbox coordinates)
    - Deduplication via text hash
    - Direct relationship to chunks and entities
    
    This is the primary unit for page-indexed RAG retrieval.
    """
    
    __tablename__ = "normalized_pages"
    
    # Identity
    page_id = Column(String, primary_key=True, index=True)
    case_id = Column(String, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    file_id = Column(String, ForeignKey("case_files.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    page_number = Column(Integer, nullable=False)
    
    # Content (immutable)
    raw_text = Column(Text, nullable=False)
    text_hash = Column(String(64), nullable=False, index=True)  # SHA-256 for deduplication
    layout_tokens = Column(JSONB, nullable=True)  # Preserve bbox coordinates from pdfplumber
    
    # Metadata
    char_count = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Indexes for efficient querying
    __table_args__ = (
        Index('idx_page_case_file', 'case_id', 'file_id', 'page_number'),
        Index('idx_page_text_hash', 'text_hash'),  # For detecting duplicate pages
        Index('idx_normalized_pages_case_user', 'case_id', 'user_id'),  # For user-scoped queries
    )
    
    # Relationships
    case = relationship("Case")
    file = relationship("CaseFile")
    chunks = relationship("DocumentChunk", back_populates="page", cascade="all, delete-orphan")
    # entity relationship via entity_sources (many-to-many)
    
    def __repr__(self):
        return f"<NormalizedPage {self.page_id} (Case: {self.case_id}, File: {self.file_id}, Page: {self.page_number})>"
    
    @staticmethod
    def generate_page_id(case_id: str, file_id: str, page_number: int) -> str:
        """Generate deterministic page ID"""
        return f"{case_id}:{file_id}:p{page_number}"
    
    @staticmethod
    def compute_text_hash(text: str) -> str:
        """Compute SHA-256 hash of text for deduplication"""
        return hashlib.sha256(text.encode('utf-8')).hexdigest()
