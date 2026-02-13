"""Page-Indexed RAG Retriever Service"""

import logging
from typing import List, Dict, Optional, Any
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.normalized_page import NormalizedPage
from app.models.page_vector import PageVector
from app.models.document_chunk import DocumentChunk
from app.services.embedding_service import embedding_service
from app.core.config import settings

logger = logging.getLogger(__name__)


class RAGContext:
    """Context object for RAG retrieval results"""
    def __init__(
        self,
        chunks: List[Any],
        total_tokens: int,
        formatted_context: str,
        source_references: List[Dict]
    ):
        self.chunks = chunks
        self.total_tokens = total_tokens
        self.formatted_context = formatted_context
        self.source_references = source_references


class PageRAGRetriever:
    """
    Page-indexed, entity-grounded RAG retriever.
    
    Implements the "Page-First" retrieval strategy:
    1. Retrieve relevant pages using whole-page embeddings (Gating)
    2. Retrieve relevant chunks from strictly those pages (Precision)
    3. Build context preserving page boundaries
    """
    
    def __init__(self):
        self.max_pages = 20  # Max pages to retrieve for context
        self.max_chunks_per_page = 5  # Max chunks per page to expand
    
    def retrieve(
        self,
        db: Session,
        query: str,
        case_id: str,
        user_id: str,
        top_k_pages: int = 10
    ) -> RAGContext:
        """
        Retrieve context for a query using page-indexed strategy.
        
        Args:
            db: Database session
            query: User question
            case_id: Case ID
            user_id: User ID
            top_k_pages: Number of pages to retrieve
            
        Returns:
            RAGContext object with formatted context and sources
        """
        # Step 1: Semantic page retrieval (Gating)
        candidate_pages = self._semantic_page_retrieval(
            db, case_id, user_id, query, top_k=top_k_pages
        )
        
        if not candidate_pages:
            logger.warning(f"No relevant pages found for query: {query}")
            return RAGContext([], 0, "", [])
            
        # Step 2: Chunk expansion (Precision)
        # We retrieve chunks only from the selected pages
        chunks = self._expand_to_chunks(
            db, candidate_pages
        )
        
        # Step 3: Rank chunks (Optional - simplified here)
        # Could rerank chunks locally if needed
        
        # Step 4: Build page-structured context
        context = self._build_page_context(chunks, candidate_pages)
        
        return context
    
    def _semantic_page_retrieval(
        self,
        db: Session,
        case_id: str,
        user_id: str,
        query: str,
        top_k: int = 10
    ) -> List[NormalizedPage]:
        """
        Retrieve relevant pages using page-level embeddings.
        """
        # Generate query embedding
        query_embedding = embedding_service.generate_query_embedding(query)
        
        # Query page vectors
        # Note: pgvector's cosine distance operator is <=>
        # Lower distance = higher similarity
        results = db.query(
            NormalizedPage,
            PageVector.embedding.cosine_distance(query_embedding).label("distance")
        ).join(
            PageVector, NormalizedPage.page_id == PageVector.page_id
        ).filter(
            PageVector.case_id == case_id,
            PageVector.user_id == user_id
        ).order_by("distance").limit(top_k).all()
        
        pages = [row[0] for row in results]
        
        logger.info(f"Page-Indexed RAG: Retrieved {len(pages)} pages for query")
        return pages

    def _expand_to_chunks(
        self,
        db: Session,
        pages: List[NormalizedPage]
    ) -> List[DocumentChunk]:
        """
        Expand selected pages to their chunks.
        """
        chunks = []
        
        # In a real implementation, we might want to be selective about chunks
        # e.g., using a local reranker or hybrid search.
        # For now, we take all chunks from the pages, up to limit.
        
        page_ids = [p.page_id for p in pages]
        
        # Optimized query
        all_chunks = db.query(DocumentChunk).filter(
            DocumentChunk.page_id.in_(page_ids)
        ).order_by(
            DocumentChunk.page_id,
            DocumentChunk.chunk_index
        ).all()
        
        chunks.extend(all_chunks)
        
        logger.info(f"Expanded {len(pages)} pages -> {len(chunks)} chunks")
        return chunks

    def _build_page_context(
        self,
        chunks: List[DocumentChunk],
        pages: List[NormalizedPage]
    ) -> RAGContext:
        """
        Build context string preserving page boundaries.
        Format:
        --- [Page X] ---
        <chunk text>
        ...
        """
        formatted_parts = []
        source_references = []
        total_tokens = 0
        
        # Group chunks by page for structured access
        chunks_by_page = {}
        for chunk in chunks:
            if chunk.page_id not in chunks_by_page:
                chunks_by_page[chunk.page_id] = []
            chunks_by_page[chunk.page_id].append(chunk)
            
        # Build context in page order (based on retrieval relevance or page number)
        # Here we follow the order of `pages` (relevance)
        for page in pages:
            page_chunks = chunks_by_page.get(page.page_id, [])
            if not page_chunks:
                continue
                
            # Add page header
            formatted_parts.append(f"\n--- [Page {page.page_number}] ---\n")
            
            # Add chunk content
            for chunk in page_chunks:
                text = chunk.chunk_text.strip()
                if text:
                    formatted_parts.append(text + "\n")
                    total_tokens += getattr(chunk, 'token_count', 0) or 0
                    
                    # Add source ref
                    source_references.append({
                        "page_id": page.page_id,
                        "file_id": page.file_id,
                        "page_number": page.page_number,
                        "chunk_id": chunk.id,
                        "bbox": chunk.bbox
                    })
        
        context_text = "".join(formatted_parts)
        
        return RAGContext(
            chunks=chunks,
            total_tokens=total_tokens,
            formatted_context=context_text,
            source_references=source_references
        )

# Singleton instance
page_rag_retriever = PageRAGRetriever()
