"""RAG retriever service for semantic search and context building"""

import logging
from typing import List, Dict, Optional, Any
from dataclasses import dataclass
from sqlalchemy.orm import Session

from app.models.document_chunk import DocumentChunk, SectionType
from app.services.embedding_service import embedding_service
from app.services.pgvector_service import pgvector_service, VectorMatch
from app.repositories.chunk_repository import chunk_repository
from app.core.config import settings

logger = logging.getLogger(__name__)

# Lazy import for reranking (optional dependency)
_reranker = None

def _get_reranker():
    """Lazily initialize reranker model"""
    global _reranker
    if _reranker is None and settings.ENABLE_RERANKING:
        try:
            from sentence_transformers import CrossEncoder
            _reranker = CrossEncoder(settings.RERANKING_MODEL)
            logger.info(f"Initialized reranker model: {settings.RERANKING_MODEL}")
        except ImportError:
            logger.warning("sentence-transformers not installed, reranking disabled")
            _reranker = False  # Mark as unavailable
        except Exception as e:
            logger.error(f"Failed to initialize reranker: {e}")
            _reranker = False
    return _reranker


@dataclass
class RetrievedChunk:
    """A chunk retrieved from RAG with full details"""
    chunk_id: str
    vector_id: str
    case_id: str
    file_id: str
    page_number: int
    section_type: SectionType
    chunk_text: str
    score: float
    char_start: int
    char_end: int
    token_count: int
    bbox: Optional[List[Dict]] = None


@dataclass
class RAGContext:
    """Context built from retrieved chunks for LLM"""
    chunks: List[RetrievedChunk]
    total_tokens: int
    formatted_context: str
    source_references: List[Dict[str, Any]]


class RAGRetriever:
    """Service for retrieving relevant chunks and building context for LLM"""

    def __init__(self):
        self.max_context_tokens = 8000  # Leave room for prompt and response

    def retrieve_for_query(
        self,
        db: Session,
        query: str,
        case_id: str,
        user_id: str,
        top_k: int = 20  # Final number of results after reranking
    ) -> List[RetrievedChunk]:
        """
        Retrieve relevant chunks for a query - all chunks, no section filtering
        Optionally applies reranking for better accuracy
        
        Args:
            db: Database session
            query: Search query
            case_id: Case to search within
            user_id: User ID for scoping
            top_k: Number of final results to return (after reranking if enabled)
            
        Returns:
            List of retrieved chunks with scores
        """
        # Generate query embedding
        query_embedding = embedding_service.generate_query_embedding(query)
        
        # Query PGVector - get more results if reranking is enabled
        initial_top_k = settings.RERANKING_TOP_K if settings.ENABLE_RERANKING else top_k
        matches = pgvector_service.query_case_chunks(
            query_vector=query_embedding,
            case_id=case_id,
            user_id=user_id,
            top_k=initial_top_k
        )
        
        # Get full chunk details from database
        vector_ids = [m.vector_id for m in matches]
        db_chunks = chunk_repository.get_by_vector_ids(db, vector_ids)
        
        # Create lookup for scores
        score_lookup = {m.vector_id: m.score for m in matches}
        
        # Build retrieved chunks
        retrieved = []
        for chunk in db_chunks:
            retrieved.append(RetrievedChunk(
                chunk_id=chunk.id,
                vector_id=chunk.vector_id,
                case_id=chunk.case_id,
                file_id=chunk.file_id,
                page_number=chunk.page_number,
                section_type=chunk.section_type,
                chunk_text=chunk.chunk_text,
                score=score_lookup.get(chunk.vector_id, 0.0),
                char_start=chunk.char_start,
                char_end=chunk.char_end,
                token_count=chunk.token_count,
                bbox=chunk.bbox
            ))
        
        # Apply reranking if enabled
        if settings.ENABLE_RERANKING and len(retrieved) > top_k:
            retrieved = self._rerank_chunks(query, retrieved, top_k)
        else:
            # Sort by score (highest first)
            retrieved.sort(key=lambda x: x.score, reverse=True)
            retrieved = retrieved[:top_k]
        
        return retrieved
    
    def _rerank_chunks(
        self,
        query: str,
        chunks: List[RetrievedChunk],
        top_k: int
    ) -> List[RetrievedChunk]:
        """
        Rerank chunks using cross-encoder model
        
        Args:
            query: Search query
            chunks: Initial retrieved chunks
            top_k: Number of results to return after reranking
            
        Returns:
            Reranked chunks
        """
        reranker = _get_reranker()
        
        # If reranker not available, fall back to original scores
        if not reranker or reranker is False:
            chunks.sort(key=lambda x: x.score, reverse=True)
            return chunks[:top_k]
        
        try:
            # Prepare pairs for reranking: (query, chunk_text)
            pairs = [[query, chunk.chunk_text] for chunk in chunks]
            
            # Get reranking scores
            rerank_scores = reranker.predict(pairs)
            
            # Combine original scores with rerank scores (weighted average)
            # Weight: 0.3 original FAISS score, 0.7 rerank score
            for i, chunk in enumerate(chunks):
                rerank_score = float(rerank_scores[i])
                # Normalize rerank score to 0-1 range (sigmoid-like)
                normalized_rerank = 1 / (1 + abs(rerank_score)) if rerank_score < 0 else rerank_score / (1 + rerank_score)
                # Weighted combination
                chunk.score = 0.3 * chunk.score + 0.7 * normalized_rerank
            
            # Sort by combined score
            chunks.sort(key=lambda x: x.score, reverse=True)
            
            return chunks[:top_k]
            
        except Exception as e:
            logger.warning(f"Reranking failed, falling back to original scores: {e}")
            chunks.sort(key=lambda x: x.score, reverse=True)
            return chunks[:top_k]

    def retrieve_section_chunks(
        self,
        db: Session,
        case_id: str,
        user_id: str,
        section_type: SectionType,  # Ignored - kept for backward compatibility
        query: Optional[str] = None,
        top_k: int = 20
    ) -> List[RetrievedChunk]:
        """
        Retrieve chunks - now returns all chunks regardless of section type
        (kept for backward compatibility but ignores section_type)
        """
        if query:
            # Use semantic search without section filter
            return self.retrieve_for_query(
                db=db,
                query=query,
                case_id=case_id,
                user_id=user_id,
                top_k=top_k
            )
        else:
            # Get all chunks for case from database
            db_chunks = chunk_repository.get_by_case_id(db, case_id)
            
            return [
                RetrievedChunk(
                    chunk_id=chunk.id,
                    vector_id=chunk.vector_id,
                    case_id=chunk.case_id,
                    file_id=chunk.file_id,
                    page_number=chunk.page_number,
                    section_type=chunk.section_type,
                    chunk_text=chunk.chunk_text,
                    score=1.0,  # No ranking without query
                    char_start=chunk.char_start,
                    char_end=chunk.char_end,
                    token_count=chunk.token_count,
                    bbox=chunk.bbox
                )
                for chunk in db_chunks
            ]

    def retrieve_all_for_case(
        self,
        db: Session,
        case_id: str
    ) -> List[RetrievedChunk]:
        """
        Retrieve all chunks for a case (for full context operations)
        
        Args:
            db: Database session
            case_id: Case ID
            
        Returns:
            All chunks for the case
        """
        db_chunks = chunk_repository.get_by_case_id(db, case_id)
        
        return [
            RetrievedChunk(
                chunk_id=chunk.id,
                vector_id=chunk.vector_id,
                case_id=chunk.case_id,
                file_id=chunk.file_id,
                page_number=chunk.page_number,
                section_type=chunk.section_type,
                chunk_text=chunk.chunk_text,
                score=1.0,
                char_start=chunk.char_start,
                char_end=chunk.char_end,
                token_count=chunk.token_count,
                bbox=chunk.bbox
            )
            for chunk in db_chunks
        ]

    def build_context(
        self,
        chunks: List[RetrievedChunk],
        max_tokens: Optional[int] = None,
        include_metadata: bool = True,
        ensure_file_diversity: bool = False
    ) -> RAGContext:
        """
        Build formatted context from retrieved chunks for LLM prompt
        
        Args:
            chunks: Retrieved chunks
            max_tokens: Maximum tokens to include
            include_metadata: Whether to include section/page metadata
            ensure_file_diversity: If True, ensures chunks from all files are included
            
        Returns:
            RAGContext with formatted text and references
        """
        max_tokens = max_tokens or self.max_context_tokens
        
        formatted_parts = []
        source_references = []
        total_tokens = 0
        included_chunks = []
        
        if ensure_file_diversity and chunks:
            # Group chunks by file_id
            chunks_by_file = {}
            for chunk in chunks:
                file_id = chunk.file_id
                if file_id not in chunks_by_file:
                    chunks_by_file[file_id] = []
                chunks_by_file[file_id].append(chunk)
            
            # Strategy: Include at least one chunk from each file first, then fill remaining space
            # This ensures all files are represented even if token limit is tight
            file_ids = list(chunks_by_file.keys())
            chunks_processed = set()  # Track which chunks we've already included
            
            # Phase 1: Include at least one chunk from each file (highest scoring first)
            for file_id in file_ids:
                file_chunks = chunks_by_file[file_id]
                # Sort by score (highest first) to get best chunk from each file
                file_chunks_sorted = sorted(file_chunks, key=lambda x: x.score, reverse=True)
                
                for chunk in file_chunks_sorted:
                    if chunk.chunk_id in chunks_processed:
                        continue
                    
                    # Check if we have room
                    if total_tokens + chunk.token_count > max_tokens:
                        # If we can't fit even one chunk from this file, try to fit a smaller one
                        # or skip if we've already included at least one chunk from this file
                        if any(c.file_id == file_id for c in included_chunks):
                            break  # Already have at least one chunk from this file
                        # Try to find a smaller chunk from this file
                        for smaller_chunk in file_chunks_sorted:
                            if smaller_chunk.chunk_id in chunks_processed:
                                continue
                            if total_tokens + smaller_chunk.token_count <= max_tokens:
                                chunk = smaller_chunk
                                break
                        else:
                            # No chunk from this file fits, but we'll try to include it in phase 2
                            break
                    
                    # Format chunk with metadata
                    if include_metadata:
                        formatted = f"\n--- Section: {chunk.section_type.value.upper()} | Page {chunk.page_number} ---\n{chunk.chunk_text}\n"
                    else:
                        formatted = f"\n{chunk.chunk_text}\n"
                    
                    formatted_parts.append(formatted)
                    total_tokens += chunk.token_count
                    included_chunks.append(chunk)
                    chunks_processed.add(chunk.chunk_id)
                    
                    # Add source reference
                    source_references.append({
                        "chunk_id": chunk.chunk_id,
                        "vector_id": chunk.vector_id,
                        "file_id": chunk.file_id,
                        "page_number": chunk.page_number,
                        "section_type": chunk.section_type.value,
                        "score": chunk.score,
                        "char_start": chunk.char_start,
                        "char_end": chunk.char_end,
                        "bbox": chunk.bbox
                    })
                    
                    # Only include one chunk per file in phase 1
                    break
            
            # Phase 2: Fill remaining space with remaining chunks (sorted by score)
            remaining_chunks = [c for c in chunks if c.chunk_id not in chunks_processed]
            remaining_chunks.sort(key=lambda x: x.score, reverse=True)
            
            for chunk in remaining_chunks:
                # Check if we have room
                if total_tokens + chunk.token_count > max_tokens:
                    continue
                
                # Format chunk with metadata
                if include_metadata:
                    formatted = f"\n--- Section: {chunk.section_type.value.upper()} | Page {chunk.page_number} ---\n{chunk.chunk_text}\n"
                else:
                    formatted = f"\n{chunk.chunk_text}\n"
                
                formatted_parts.append(formatted)
                total_tokens += chunk.token_count
                included_chunks.append(chunk)
                
                # Add source reference
                source_references.append({
                    "chunk_id": chunk.chunk_id,
                    "vector_id": chunk.vector_id,
                    "file_id": chunk.file_id,
                    "page_number": chunk.page_number,
                    "section_type": chunk.section_type.value,
                    "score": chunk.score,
                    "char_start": chunk.char_start,
                    "char_end": chunk.char_end,
                    "bbox": chunk.bbox
                })
        else:
            # Original behavior: sequential inclusion
            for chunk in chunks:
                # Check if we have room
                if total_tokens + chunk.token_count > max_tokens:
                    continue
                
                # Format chunk with metadata
                if include_metadata:
                    formatted = f"\n--- Section: {chunk.section_type.value.upper()} | Page {chunk.page_number} ---\n{chunk.chunk_text}\n"
                else:
                    formatted = f"\n{chunk.chunk_text}\n"
                
                formatted_parts.append(formatted)
                total_tokens += chunk.token_count
                included_chunks.append(chunk)
                
                # Add source reference
                source_references.append({
                    "chunk_id": chunk.chunk_id,
                    "vector_id": chunk.vector_id,
                    "file_id": chunk.file_id,
                    "page_number": chunk.page_number,
                    "section_type": chunk.section_type.value,
                    "score": chunk.score,
                    "char_start": chunk.char_start,
                    "char_end": chunk.char_end,
                    "bbox": chunk.bbox
                })
        
        formatted_context = "".join(formatted_parts)
        
        return RAGContext(
            chunks=included_chunks,
            total_tokens=total_tokens,
            formatted_context=formatted_context,
            source_references=source_references
        )

    def build_section_context(
        self,
        db: Session,
        case_id: str,
        user_id: str,
        section_types: List[SectionType],  # Kept for backward compatibility but ignored
        query: Optional[str] = None,
        max_tokens: Optional[int] = None,
        ensure_file_diversity: bool = False
    ) -> RAGContext:
        """
        Build context from all chunks - section_types parameter is ignored
        (kept for backward compatibility)
        
        Args:
            db: Database session
            case_id: Case ID
            user_id: User ID for scoping
            section_types: Ignored - all chunks are retrieved
            query: Optional query for relevance ranking
            max_tokens: Maximum tokens
            ensure_file_diversity: If True, ensures chunks from all files are included
            
        Returns:
            RAGContext for all relevant chunks
        """
        if query:
            # Use semantic search to get most relevant chunks
            all_chunks = self.retrieve_for_query(
                db=db,
                query=query,
                case_id=case_id,
                user_id=user_id,
                top_k=30  # Increased to get more context
            )
        else:
            # Get all chunks for case
            all_chunks = self.retrieve_all_for_case(db, case_id)
        
        # Sort by score if query was used, otherwise by page number
        if query:
            all_chunks.sort(key=lambda x: x.score, reverse=True)
        else:
            all_chunks.sort(key=lambda x: (x.page_number, x.char_start))
        
        # Pass ensure_file_diversity to build_context
        return self.build_context(all_chunks, max_tokens, ensure_file_diversity=ensure_file_diversity)

    def get_chunk_by_id(
        self,
        db: Session,
        chunk_id: str
    ) -> Optional[RetrievedChunk]:
        """
        Get a specific chunk by ID
        
        Args:
            db: Database session
            chunk_id: Chunk ID
            
        Returns:
            Retrieved chunk or None
        """
        chunk = chunk_repository.get_by_id(db, chunk_id)
        
        if not chunk:
            return None
        
        return RetrievedChunk(
            chunk_id=chunk.id,
            vector_id=chunk.vector_id,
            case_id=chunk.case_id,
            file_id=chunk.file_id,
            page_number=chunk.page_number,
            section_type=chunk.section_type,
            chunk_text=chunk.chunk_text,
            score=1.0,
            char_start=chunk.char_start,
            char_end=chunk.char_end,
            token_count=chunk.token_count
        )

    def get_chunk_by_vector_id(
        self,
        db: Session,
        vector_id: str
    ) -> Optional[RetrievedChunk]:
        """
        Get a specific chunk by vector ID
        
        Args:
            db: Database session
            vector_id: Vector database ID (FAISS)
            
        Returns:
            Retrieved chunk or None
        """
        chunk = chunk_repository.get_by_vector_id(db, vector_id)
        
        if not chunk:
            return None
        
        return RetrievedChunk(
            chunk_id=chunk.id,
            vector_id=chunk.vector_id,
            case_id=chunk.case_id,
            file_id=chunk.file_id,
            page_number=chunk.page_number,
            section_type=chunk.section_type,
            chunk_text=chunk.chunk_text,
            score=1.0,
            char_start=chunk.char_start,
            char_end=chunk.char_end,
            token_count=chunk.token_count
        )


# Singleton instance
rag_retriever = RAGRetriever()

