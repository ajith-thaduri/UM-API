"""Unit tests for PGVectorService"""

import pytest
from unittest.mock import MagicMock, patch, Mock
from sqlalchemy.orm import Session
from app.services.pgvector_service import PGVectorService, VectorMatch
from app.models.document_chunk import DocumentChunk, SectionType


@pytest.fixture
def pgvector_service():
    return PGVectorService()


@pytest.fixture
def mock_db():
    return MagicMock(spec=Session)


@pytest.fixture
def mock_chunk():
    """Mock DocumentChunk"""
    chunk = MagicMock(spec=DocumentChunk)
    chunk.id = "chunk-1"
    chunk.vector_id = "vec-1"
    chunk.case_id = "case-1"
    chunk.file_id = "file-1"
    chunk.page_number = 1
    chunk.chunk_index = 0
    chunk.section_type = SectionType.CLINICAL
    chunk.token_count = 10
    chunk.chunk_text = "Test chunk text"
    return chunk


def test_upsert_chunks(pgvector_service):
    """Test upsert_chunks (no-op method)"""
    vectors = [{"id": "v1"}, {"id": "v2"}]
    result = pgvector_service.upsert_chunks("case-1", vectors)
    assert result == 2


def test_query_success(pgvector_service, mock_db, mock_chunk):
    """Test successful vector query"""
    query_vector = [0.1] * 1536
    
    with patch("app.services.pgvector_service.SessionLocal", return_value=mock_db), \
         patch("app.services.pgvector_service.chunk_repository.search_similar", return_value=[mock_chunk]):
        
        results = pgvector_service.query(
            case_id="case-1",
            query_vector=query_vector,
            user_id="user-1",
            top_k=10
        )
        
        assert len(results) == 1
        assert isinstance(results[0], VectorMatch)
        assert results[0].vector_id == "vec-1"
        assert results[0].score == 0.9  # Placeholder score
        assert results[0].metadata["case_id"] == "case-1"
        assert results[0].metadata["file_id"] == "file-1"
        assert results[0].text_preview == "Test chunk text"


def test_query_missing_user_id(pgvector_service):
    """Test that query requires user_id"""
    with pytest.raises(ValueError, match="user_id is required"):
        pgvector_service.query(
            case_id="case-1",
            query_vector=[0.1] * 1536,
            user_id=None
        )


def test_query_with_filters(pgvector_service, mock_db, mock_chunk):
    """Test query with metadata filters"""
    query_vector = [0.1] * 1536
    filter_dict = {"section_type": SectionType.LABS}
    
    with patch("app.services.pgvector_service.SessionLocal", return_value=mock_db), \
         patch("app.services.pgvector_service.chunk_repository.search_similar", return_value=[mock_chunk]) as mock_search:
        
        pgvector_service.query(
            case_id="case-1",
            query_vector=query_vector,
            user_id="user-1",
            top_k=10,
            filter_dict=filter_dict
        )
        
        # Verify filter was passed
        call_args = mock_search.call_args
        assert call_args[1]["filter_dict"]["section_type"] == SectionType.LABS
        assert call_args[1]["filter_dict"]["case_id"] == "case-1"
        assert call_args[1]["filter_dict"]["user_id"] == "user-1"


def test_query_case_chunks(pgvector_service, mock_db, mock_chunk):
    """Test query_case_chunks convenience method"""
    query_vector = [0.1] * 1536
    
    with patch("app.services.pgvector_service.SessionLocal", return_value=mock_db), \
         patch("app.services.pgvector_service.chunk_repository.search_similar", return_value=[mock_chunk]):
        
        results = pgvector_service.query_case_chunks(
            query_vector=query_vector,
            case_id="case-1",
            user_id="user-1",
            top_k=20
        )
        
        assert len(results) == 1
        assert isinstance(results[0], VectorMatch)


def test_delete_case_chunks(pgvector_service, mock_db):
    """Test deleting chunks for a case"""
    with patch("app.services.pgvector_service.SessionLocal", return_value=mock_db), \
         patch("app.services.pgvector_service.chunk_repository.delete_by_case_id", return_value=5):
        
        result = pgvector_service.delete_case_chunks("case-1", user_id="user-1")
        assert result == 5


def test_flush_to_s3(pgvector_service):
    """Test flush_to_s3 (no-op method)"""
    result = pgvector_service.flush_to_s3("case-1", user_id="user-1")
    assert result is True


def test_query_multiple_results(pgvector_service, mock_db):
    """Test query with multiple results"""
    query_vector = [0.1] * 1536
    
    # Create multiple mock chunks
    chunks = []
    for i in range(3):
        chunk = MagicMock(spec=DocumentChunk)
        chunk.id = f"chunk-{i}"
        chunk.vector_id = f"vec-{i}"
        chunk.case_id = "case-1"
        chunk.file_id = f"file-{i}"
        chunk.page_number = i + 1
        chunk.chunk_index = i
        chunk.section_type = SectionType.CLINICAL
        chunk.token_count = 10
        chunk.chunk_text = f"Chunk {i} text"
        chunks.append(chunk)
    
    with patch("app.services.pgvector_service.SessionLocal", return_value=mock_db), \
         patch("app.services.pgvector_service.chunk_repository.search_similar", return_value=chunks):
        
        results = pgvector_service.query(
            case_id="case-1",
            query_vector=query_vector,
            user_id="user-1",
            top_k=10
        )
        
        assert len(results) == 3
        assert all(isinstance(r, VectorMatch) for r in results)
        assert results[0].vector_id == "vec-0"
        assert results[1].vector_id == "vec-1"
        assert results[2].vector_id == "vec-2"


def test_query_empty_results(pgvector_service, mock_db):
    """Test query with no results"""
    query_vector = [0.1] * 1536
    
    with patch("app.services.pgvector_service.SessionLocal", return_value=mock_db), \
         patch("app.services.pgvector_service.chunk_repository.search_similar", return_value=[]):
        
        results = pgvector_service.query(
            case_id="case-1",
            query_vector=query_vector,
            user_id="user-1",
            top_k=10
        )
        
        assert len(results) == 0
