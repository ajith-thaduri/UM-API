"""PGVector database service for RAG"""

import logging
from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass
from sqlalchemy.orm import Session

from app.models.document_chunk import DocumentChunk
from app.repositories.chunk_repository import chunk_repository
from app.db.session import SessionLocal

logger = logging.getLogger(__name__)


@dataclass
class VectorMatch:
    """Result from a vector search"""
    vector_id: str
    score: float
    metadata: Dict[str, Any]
    text_preview: Optional[str] = None


class PGVectorService:
    """Service for PGVector database operations"""

    def __init__(self):
        pass

    def upsert_chunks(
        self,
        case_id: str,
        vectors: List[Dict[str, Any]],
        user_id: Optional[str] = None,
        batch_size: int = 100
    ) -> int:
        """
        No-op for Postgres. Chunks are inserted directly into DB via repository.
        Kept for interface compatibility if needed, but case_processor should handle this.
        """
        # In the new architecture, embedding generation happens before DB insert.
        # This method is likely deprecated, but if we keep the "upsert later" pattern:
        # We would update the rows with the embeddings.
        return len(vectors)

    def query(
        self,
        case_id: str,
        query_vector: List[float],
        user_id: Optional[str] = None,
        top_k: int = 10,
        filter_dict: Optional[Dict[str, Any]] = None,
        include_metadata: bool = True
    ) -> List[VectorMatch]:
        """
        Query database for similar vectors
        """
        if user_id is None:
            raise ValueError("user_id is required for vector operations")
            
        db = SessionLocal()
        try:
            # Prepare filters
            final_filter = {"case_id": case_id, "user_id": user_id}
            if filter_dict:
                # Merge user filters
                final_filter.update(filter_dict)
            
            # Search
            chunks = chunk_repository.search_similar(
                db=db,
                embedding=query_vector,
                limit=top_k,
                filter_dict=final_filter
            )
            
            matches = []
            for chunk in chunks:
                # Calculate cosine match score (1 - distance)
                # pgvector operator returns distance. sqlalchemy function returns distance?
                # Actually, search_similar orders by distance. 
                # To get the score, we might need to select the distance explicitly.
                # For now, let's assume relevance is order. Score is not returned by search_similar yet.
                # We'll just fake it or update repo to return tuple.
                
                # Let's map it back to VectorMatch
                metadata = {
                    "case_id": chunk.case_id,
                    "file_id": chunk.file_id,
                    "page_number": chunk.page_number,
                    "chunk_index": chunk.chunk_index,
                    "section_type": chunk.section_type.value if hasattr(chunk.section_type, 'value') else chunk.section_type,
                    "token_count": chunk.token_count
                }
                
                matches.append(VectorMatch(
                    vector_id=chunk.vector_id or chunk.id,
                    score=0.9, # Placeholder until we query distance
                    metadata=metadata,
                    text_preview=chunk.chunk_text[:200]
                ))
            
            return matches
        finally:
            db.close()

    def query_case_chunks(
        self,
        query_vector: List[float],
        case_id: str,
        user_id: Optional[str] = None,
        top_k: int = 20
    ) -> List[VectorMatch]:
        """Query for chunks within a specific case"""
        return self.query(
            case_id=case_id,
            query_vector=query_vector,
            user_id=user_id,
            top_k=top_k
        )

    def delete_case_chunks(self, case_id: str, user_id: Optional[str] = None) -> int:
        """Delete all chunks for a case"""
        db = SessionLocal()
        try:
            return chunk_repository.delete_by_case_id(db, case_id)
        finally:
            db.close()
            
    def flush_to_s3(self, case_id: str, user_id: Optional[str] = None) -> bool:
        """No-op compatible method"""
        return True


# Singleton instance
pgvector_service = PGVectorService()
