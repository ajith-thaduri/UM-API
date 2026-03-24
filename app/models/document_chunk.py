"""Document chunk model for RAG"""

import enum
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, Integer, Text, Enum, JSON, Index
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector

from app.db.session import Base


class SectionType(str, enum.Enum):
    """Section types for medical document chunks"""
    MEDICATIONS = "medications"
    LABS = "labs"
    DIAGNOSES = "diagnoses"
    PROCEDURES = "procedures"
    VITALS = "vitals"
    ALLERGIES = "allergies"
    IMAGING = "imaging"
    HISTORY = "history"
    SOCIAL = "social"
    THERAPY = "therapy"
    CLINICAL = "clinical"
    UNKNOWN = "unknown"


class DocumentChunk(Base):
    """Document chunk model for vector storage and RAG"""

    __tablename__ = "document_chunks"

    id = Column(String, primary_key=True, index=True)
    case_id = Column(String, ForeignKey("cases.id"), nullable=False, index=True)
    case_version_id = Column(
        String, ForeignKey("case_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    file_id = Column(String, ForeignKey("case_files.id"), nullable=False, index=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Chunk positioning
    chunk_index = Column(Integer, nullable=False)
    page_number = Column(Integer, nullable=False)
    
    # Section classification
    # Using native_enum=False to store as VARCHAR to avoid PostgreSQL enum value mismatches
    section_type = Column(
        Enum(SectionType, native_enum=False, length=50),
        default=SectionType.UNKNOWN,
        nullable=False
    )
    
    # Chunk content
    chunk_text = Column(Text, nullable=False)
    char_start = Column(Integer, nullable=False)
    char_end = Column(Integer, nullable=False)
    token_count = Column(Integer, nullable=False)
    
    # Embedding vector (1536 dimensions for OpenAI text-embedding-3-small)
    embedding = Column(Vector(1536), nullable=True)
    
    # Bounding box coordinates for precise PDF highlighting
    # Format: {"x0": float, "y0": float, "x1": float, "y1": float}
    # Coordinates are in PDF points (1/72 inch)
    bbox = Column(JSON, nullable=True)  # Optional for backward compatibility

    # Word-level segments for term-precise highlighting.
    # Format: [{"text": str, "bbox": {"x0", "y0", "x1", "y1"}}, ...]
    # Populated by chunk_page_with_bbox; allows find_term_bbox() to locate any
    # extracted term within this chunk at render time without re-reading the PDF.
    word_segments = Column(JSON, nullable=True)
    
    # Vector database reference (FAISS)
    vector_id = Column(String, unique=True, nullable=False, index=True)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Performance indexes
    __table_args__ = (
        Index('idx_chunk_case_section', 'case_id', 'section_type'),
        Index('idx_chunk_version_section', 'case_version_id', 'section_type'),
        Index('idx_chunk_file_page', 'file_id', 'page_number'),
        Index(
            'idx_embedding_cosine',
            'embedding',
            postgresql_using='hnsw',
            postgresql_with={'m': 16, 'ef_construction': 64},
            postgresql_ops={'embedding': 'vector_cosine_ops'}
        ),
    )
    
    # Relationships
    case = relationship("Case", backref="chunks")
    case_version = relationship("CaseVersion", backref="document_chunks")
    file = relationship("CaseFile", backref="chunks")

    def __repr__(self):
        return f"<DocumentChunk {self.id} (Case: {self.case_id}, Page: {self.page_number}, Section: {self.section_type})>"

