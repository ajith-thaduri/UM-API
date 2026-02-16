from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.models.document_chunk import DocumentChunk, SectionType
from app.repositories.base import BaseRepository


class ChunkRepository(BaseRepository[DocumentChunk]):
    """Repository for DocumentChunk operations"""

    def __init__(self):
        super().__init__(DocumentChunk)

    def get_by_vector_id(self, db: Session, vector_id: str) -> Optional[DocumentChunk]:
        """Get chunk by vector ID"""
        return db.query(DocumentChunk).filter(
            DocumentChunk.vector_id == vector_id
        ).first()

    def get_by_case_id(self, db: Session, case_id: str) -> List[DocumentChunk]:
        """Get all chunks for a case"""
        return db.query(DocumentChunk).filter(
            DocumentChunk.case_id == case_id
        ).order_by(
            DocumentChunk.file_id,
            DocumentChunk.page_number,
            DocumentChunk.chunk_index
        ).all()

    def get_by_file_id(self, db: Session, file_id: str) -> List[DocumentChunk]:
        """Get all chunks for a file"""
        return db.query(DocumentChunk).filter(
            DocumentChunk.file_id == file_id
        ).order_by(
            DocumentChunk.page_number,
            DocumentChunk.chunk_index
        ).all()

    def get_by_section(
        self,
        db: Session,
        case_id: str,
        section_type: SectionType
    ) -> List[DocumentChunk]:
        """Get chunks by section type for a case"""
        return db.query(DocumentChunk).filter(
            DocumentChunk.case_id == case_id,
            DocumentChunk.section_type == section_type
        ).order_by(
            DocumentChunk.file_id,
            DocumentChunk.page_number,
            DocumentChunk.chunk_index
        ).all()

    def get_by_page(
        self,
        db: Session,
        file_id: str,
        page_number: int
    ) -> List[DocumentChunk]:
        """Get chunks for a specific page"""
        return db.query(DocumentChunk).filter(
            DocumentChunk.file_id == file_id,
            DocumentChunk.page_number == page_number
        ).order_by(DocumentChunk.chunk_index).all()

    def get_by_vector_ids(
        self,
        db: Session,
        vector_ids: List[str]
    ) -> List[DocumentChunk]:
        """Get multiple chunks by their vector IDs"""
        if not vector_ids:
            return []
        return db.query(DocumentChunk).filter(
            DocumentChunk.vector_id.in_(vector_ids)
        ).all()

    def delete_by_case_id(self, db: Session, case_id: str) -> int:
        """Delete all chunks for a case"""
        count = db.query(DocumentChunk).filter(
            DocumentChunk.case_id == case_id
        ).delete()
        db.commit()
        return count
    
    def count_by_case(self, db: Session, case_id: str) -> int:
        """Count total chunks for a case"""
        return db.query(DocumentChunk).filter(
            DocumentChunk.case_id == case_id
        ).count()

    def delete_by_file_id(self, db: Session, file_id: str) -> int:
        """Delete all chunks for a file"""
        count = db.query(DocumentChunk).filter(
            DocumentChunk.file_id == file_id
        ).delete()
        db.commit()
        return count

    def count_by_case(self, db: Session, case_id: str) -> int:
        """Count chunks for a case"""
        return db.query(DocumentChunk).filter(
            DocumentChunk.case_id == case_id
        ).count()

    def count_by_section(
        self,
        db: Session,
        case_id: str,
        section_type: SectionType
    ) -> int:
        """Count chunks by section type for a case"""
        return db.query(DocumentChunk).filter(
            DocumentChunk.case_id == case_id,
            DocumentChunk.section_type == section_type
        ).count()

    def bulk_create(self, db: Session, chunks: List[DocumentChunk], batch_size: int = 100) -> int:
        """
        Bulk create chunks using optimized SQLAlchemy bulk_insert_mappings.
        This provides ~10x performance improvement over standard add_all().
        
        Args:
            db: Database session
            chunks: List of DocumentChunk objects to create
            batch_size: Number of chunks per batch (default 100)
        
        Returns:
            Number of chunks inserted
        """
        import logging
        from sqlalchemy.exc import OperationalError
        
        logger = logging.getLogger(__name__)
        total = len(chunks)
        
        if total == 0:
            return 0
        
        logger.info(f"Bulk inserting {total} chunks in batches of {batch_size}")
        
        # Convert objects to dictionaries for bulk_insert_mappings
        # This allows us to use the Core engine for maximum speed
        # We must explicitly handle potential None values that would be defaults
        chunk_dicts = []
        for chunk in chunks:
            # Manually build dict to avoid overhead of chunk.__dict__
            c_dict = {
                "id": chunk.id,
                "case_id": chunk.case_id,
                "user_id": chunk.user_id,
                "file_id": chunk.file_id,
                "vector_id": chunk.vector_id,
                "chunk_index": chunk.chunk_index,
                "page_number": chunk.page_number,
                "section_type": chunk.section_type,
                "chunk_text": chunk.chunk_text,
                "char_start": chunk.char_start,
                "char_end": chunk.char_end,
                "token_count": chunk.token_count,
                "bbox": chunk.bbox,
                "created_at": chunk.created_at,
                "embedding": chunk.embedding
            }
            chunk_dicts.append(c_dict)
            
        for i in range(0, total, batch_size):
            batch = chunk_dicts[i:i + batch_size]
            batch_num = (i // batch_size) + 1
            total_batches = (total + batch_size - 1) // batch_size
            
            try:
                # bulk_insert_mappings is the fastest way to insert rows using SQLAlchemy Core
                db.bulk_insert_mappings(DocumentChunk, batch)
                # No flush needed for Core operations usually, but good to keep transaction clean
                logger.info(f"Inserted batch {batch_num}/{total_batches} ({len(batch)} chunks)")
            except OperationalError as e:
                logger.error(f"Connection error in batch {batch_num}/{total_batches}: {e}")
                db.rollback()
                raise
        
        # Commit handled by caller or at end
        try:
            db.commit()
            logger.info(f"Successfully committed {total} chunks via fast bulk insert")
        except Exception as e:
            db.rollback()
            raise
            
        return total

    def search_similar(
        self,
        db: Session,
        embedding: List[float],
        limit: int = 10,
        filter_dict: Optional[Dict[str, Any]] = None
    ) -> List[DocumentChunk]:
        """
        Search for similar chunks using vector similarity
        
        Args:
            db: Database session
            embedding: Query embedding vector
            limit: Number of results to return
            filter_dict: filters (e.g. {"case_id": "123", "section_type": {"$in": ["medns"]}})
            
        Returns:
            List of matching DocumentChunks ordered by similarity
        """
        # Start query
        query = db.query(DocumentChunk)
        
        # Apply filters
        if filter_dict:
            for key, condition in filter_dict.items():
                if isinstance(condition, dict):
                    # Handle special operators
                    if "$eq" in condition:
                        query = query.filter(getattr(DocumentChunk, key) == condition["$eq"])
                    elif "$in" in condition:
                        query = query.filter(getattr(DocumentChunk, key).in_(condition["$in"]))
                else:
                    # Direct equality
                    query = query.filter(getattr(DocumentChunk, key) == condition)

        # Order by cosine distance (nearest neighbors)
        # using the <=> operator or .cosine_distance method from pgvector
        query = query.order_by(DocumentChunk.embedding.cosine_distance(embedding))
        
        return query.limit(limit).all()



# Singleton instance
chunk_repository = ChunkRepository()
