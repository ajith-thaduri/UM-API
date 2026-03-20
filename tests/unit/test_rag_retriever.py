import pytest
from unittest.mock import MagicMock, patch
from sqlalchemy.orm import Session
from app.services.rag_retriever import RAGRetriever, RetrievedChunk, RAGContext
from app.models.document_chunk import SectionType, DocumentChunk

@pytest.fixture
def rag_retriever():
    return RAGRetriever()

@pytest.fixture
def mock_db():
    return MagicMock(spec=Session)

def test_build_context_basic(rag_retriever):
    chunks = [
        RetrievedChunk(
            chunk_id="c1", vector_id="v1", case_id="case1", file_id="f1",
            page_number=1, section_type=SectionType.CLINICAL,
            chunk_text="Text 1", score=0.9, char_start=0, char_end=6, token_count=2
        ),
        RetrievedChunk(
            chunk_id="c2", vector_id="v2", case_id="case1", file_id="f1",
            page_number=2, section_type=SectionType.LABS,
            chunk_text="Text 2", score=0.8, char_start=0, char_end=6, token_count=2
        )
    ]
    
    context = rag_retriever.build_context(chunks)
    
    assert isinstance(context, RAGContext)
    assert context.total_tokens == 4
    assert "Text 1" in context.formatted_context
    assert "Text 2" in context.formatted_context
    assert len(context.source_references) == 2

def test_build_context_token_limit(rag_retriever):
    chunks = [
        RetrievedChunk(
            chunk_id="c1", vector_id="v1", case_id="case1", file_id="f1",
            page_number=1, section_type=SectionType.CLINICAL,
            chunk_text="Text 1", score=0.9, char_start=0, char_end=6, token_count=100
        ),
        RetrievedChunk(
            chunk_id="c2", vector_id="v2", case_id="case1", file_id="f1",
            page_number=2, section_type=SectionType.LABS,
            chunk_text="Text 2", score=0.8, char_start=0, char_end=6, token_count=100
        )
    ]
    
    context = rag_retriever.build_context(chunks, max_tokens=150)
    
    assert len(context.chunks) == 1
    assert context.total_tokens == 100

def test_retrieve_for_query(rag_retriever, mock_db):
    mock_matches = [MagicMock(vector_id="v1", score=0.9)]
    mock_chunk = MagicMock(spec=DocumentChunk)
    mock_chunk.id = "c1"
    mock_chunk.vector_id = "v1"
    mock_chunk.case_id = "case1"
    mock_chunk.file_id = "f1"
    mock_chunk.page_number = 1
    mock_chunk.section_type = SectionType.CLINICAL
    mock_chunk.chunk_text = "Text 1"
    mock_chunk.char_start = 0
    mock_chunk.char_end = 6
    mock_chunk.token_count = 2
    mock_chunk.bbox = None

    with patch("app.services.rag_retriever.embedding_service.generate_query_embedding", return_value=[0.1]*1536), \
         patch("app.services.rag_retriever.pgvector_service.query_case_chunks", return_value=mock_matches), \
         patch("app.services.rag_retriever.chunk_repository.get_by_vector_ids", return_value=[mock_chunk]):
        
        results = rag_retriever.retrieve_for_query(mock_db, "query", "case1", "user1")
        
        assert len(results) == 1
        assert results[0].chunk_id == "c1"
        assert results[0].score == 0.9

def test_build_section_context(rag_retriever, mock_db):
    chunks = [
        RetrievedChunk(
            chunk_id="c1", vector_id="v1", case_id="case1", file_id="f1",
            page_number=1, section_type=SectionType.CLINICAL,
            chunk_text="Text 1", score=0.9, char_start=0, char_end=6, token_count=2
        )
    ]
    
    with patch.object(rag_retriever, "retrieve_for_query", return_value=chunks):
        context = rag_retriever.build_section_context(mock_db, "case1", "user1", [], query="test")
        assert "Text 1" in context.formatted_context


def test_rerank_chunks(rag_retriever):
    """Test reranking of chunks using cross-encoder"""
    chunks = [
        RetrievedChunk(
            chunk_id="c1", vector_id="v1", case_id="case1", file_id="f1",
            page_number=1, section_type=SectionType.CLINICAL,
            chunk_text="Patient has hypertension", score=0.7, char_start=0, char_end=25, token_count=5
        ),
        RetrievedChunk(
            chunk_id="c2", vector_id="v2", case_id="case1", file_id="f1",
            page_number=2, section_type=SectionType.LABS,
            chunk_text="Blood pressure is normal", score=0.8, char_start=0, char_end=25, token_count=5
        ),
        RetrievedChunk(
            chunk_id="c3", vector_id="v3", case_id="case1", file_id="f1",
            page_number=3, section_type=SectionType.CLINICAL,
            chunk_text="Hypertension diagnosis confirmed", score=0.6, char_start=0, char_end=30, token_count=5
        )
    ]
    
    # Mock reranker
    mock_reranker = MagicMock()
    mock_reranker.predict.return_value = [0.9, 0.5, 0.8]  # Rerank scores
    
    with patch("app.services.rag_retriever._get_reranker", return_value=mock_reranker):
        reranked = rag_retriever._rerank_chunks("hypertension", chunks, top_k=2)
        
        assert len(reranked) == 2
        # After reranking, scores should be updated
        assert all(chunk.score > 0 for chunk in reranked)
        # Should be sorted by combined score
        assert reranked[0].score >= reranked[1].score


def test_rerank_chunks_fallback(rag_retriever):
    """Test reranking fallback when reranker unavailable"""
    chunks = [
        RetrievedChunk(
            chunk_id="c1", vector_id="v1", case_id="case1", file_id="f1",
            page_number=1, section_type=SectionType.CLINICAL,
            chunk_text="Text 1", score=0.9, char_start=0, char_end=6, token_count=5
        ),
        RetrievedChunk(
            chunk_id="c2", vector_id="v2", case_id="case1", file_id="f1",
            page_number=2, section_type=SectionType.LABS,
            chunk_text="Text 2", score=0.8, char_start=0, char_end=6, token_count=5
        )
    ]
    
    # Mock reranker as unavailable
    with patch("app.services.rag_retriever._get_reranker", return_value=False):
        reranked = rag_retriever._rerank_chunks("query", chunks, top_k=2)
        
        # Should fall back to original scores, sorted
        assert len(reranked) == 2
        assert reranked[0].score == 0.9
        assert reranked[1].score == 0.8


def test_build_context_file_diversity(rag_retriever):
    """Test build_context with ensure_file_diversity=True"""
    chunks = [
        RetrievedChunk(
            chunk_id="c1", vector_id="v1", case_id="case1", file_id="f1",
            page_number=1, section_type=SectionType.CLINICAL,
            chunk_text="File 1 chunk 1", score=0.9, char_start=0, char_end=15, token_count=3
        ),
        RetrievedChunk(
            chunk_id="c2", vector_id="v2", case_id="case1", file_id="f1",
            page_number=2, section_type=SectionType.CLINICAL,
            chunk_text="File 1 chunk 2", score=0.8, char_start=0, char_end=15, token_count=3
        ),
        RetrievedChunk(
            chunk_id="c3", vector_id="v3", case_id="case1", file_id="f2",
            page_number=1, section_type=SectionType.LABS,
            chunk_text="File 2 chunk 1", score=0.7, char_start=0, char_end=15, token_count=3
        ),
        RetrievedChunk(
            chunk_id="c4", vector_id="v4", case_id="case1", file_id="f2",
            page_number=2, section_type=SectionType.LABS,
            chunk_text="File 2 chunk 2", score=0.6, char_start=0, char_end=15, token_count=3
        )
    ]
    
    context = rag_retriever.build_context(chunks, max_tokens=20, ensure_file_diversity=True)
    
    # Should include chunks from both files
    assert len(context.chunks) >= 2
    file_ids = {chunk.file_id for chunk in context.chunks}
    assert "f1" in file_ids
    assert "f2" in file_ids


def test_build_context_file_diversity_token_limit(rag_retriever):
    """Test file diversity respects token limits"""
    chunks = [
        RetrievedChunk(
            chunk_id="c1", vector_id="v1", case_id="case1", file_id="f1",
            page_number=1, section_type=SectionType.CLINICAL,
            chunk_text="File 1", score=0.9, char_start=0, char_end=6, token_count=50
        ),
        RetrievedChunk(
            chunk_id="c2", vector_id="v2", case_id="case1", file_id="f2",
            page_number=1, section_type=SectionType.LABS,
            chunk_text="File 2", score=0.8, char_start=0, char_end=6, token_count=50
        ),
        RetrievedChunk(
            chunk_id="c3", vector_id="v3", case_id="case1", file_id="f3",
            page_number=1, section_type=SectionType.CLINICAL,
            chunk_text="File 3", score=0.7, char_start=0, char_end=6, token_count=50
        )
    ]
    
    # Token limit is 100, but we have 3 files with 50 tokens each
    # Should include at least one chunk from each file if possible
    context = rag_retriever.build_context(chunks, max_tokens=100, ensure_file_diversity=True)
    
    # Should include chunks but respect token limit
    assert context.total_tokens <= 100
    assert len(context.chunks) >= 1


def test_retrieve_all_for_case(rag_retriever, mock_db):
    """Test retrieving all chunks for a case"""
    mock_chunks = [
        MagicMock(spec=DocumentChunk),
        MagicMock(spec=DocumentChunk)
    ]
    mock_chunks[0].id = "c1"
    mock_chunks[0].vector_id = "v1"
    mock_chunks[0].case_id = "case1"
    mock_chunks[0].file_id = "f1"
    mock_chunks[0].page_number = 1
    mock_chunks[0].section_type = SectionType.CLINICAL
    mock_chunks[0].chunk_text = "Text 1"
    mock_chunks[0].char_start = 0
    mock_chunks[0].char_end = 6
    mock_chunks[0].token_count = 2
    mock_chunks[0].bbox = None
    
    mock_chunks[1].id = "c2"
    mock_chunks[1].vector_id = "v2"
    mock_chunks[1].case_id = "case1"
    mock_chunks[1].file_id = "f1"
    mock_chunks[1].page_number = 2
    mock_chunks[1].section_type = SectionType.LABS
    mock_chunks[1].chunk_text = "Text 2"
    mock_chunks[1].char_start = 0
    mock_chunks[1].char_end = 6
    mock_chunks[1].token_count = 2
    mock_chunks[1].bbox = None
    
    with patch("app.services.rag_retriever.chunk_repository.get_by_case_id", return_value=mock_chunks):
        results = rag_retriever.retrieve_all_for_case(mock_db, "case1")
        
        assert len(results) == 2
        assert all(isinstance(r, RetrievedChunk) for r in results)
        assert results[0].chunk_id == "c1"
        assert results[1].chunk_id == "c2"
