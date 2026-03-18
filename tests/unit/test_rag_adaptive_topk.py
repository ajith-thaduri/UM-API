"""
Unit tests for RAG adaptive top_k functionality
"""

import pytest
from unittest.mock import Mock, patch
from app.services.rag_retriever import rag_retriever
from app.repositories.chunk_repository import chunk_repository


class TestAdaptiveTopK:
    """Test suite for adaptive top_k computation"""
    
    def test_small_document_adaptive_topk(self, db_session):
        """Test adaptive top_k for small documents (<50 chunks)"""
        # Mock chunk count
        with patch.object(chunk_repository, 'count_by_case', return_value=20):
            adaptive_k = rag_retriever._compute_adaptive_top_k(
                db=db_session,
                case_id="test-case-id",
                base_top_k=20
            )
            
            # For 20 chunks, should retrieve up to base_top_k * 2 (40) but capped at total (20)
            assert adaptive_k == 20
            assert adaptive_k >= 20  # At least min_top_k
    
    def test_medium_document_adaptive_topk(self, db_session):
        """Test adaptive top_k for medium documents (50-200 chunks)"""
        # Mock chunk count - 100 chunks
        with patch.object(chunk_repository, 'count_by_case', return_value=100):
            adaptive_k = rag_retriever._compute_adaptive_top_k(
                db=db_session,
                case_id="test-case-id",
                base_top_k=30
            )
            
            # For 100 chunks, should retrieve ~50% = 50 chunks
            assert adaptive_k == 50
            assert 40 <= adaptive_k <= 60  # Allow some range
    
    def test_large_document_adaptive_topk(self, db_session):
        """Test adaptive top_k for large documents (>200 chunks)"""
        # Mock chunk count - 500 chunks
        with patch.object(chunk_repository, 'count_by_case', return_value=500):
            adaptive_k = rag_retriever._compute_adaptive_top_k(
                db=db_session,
                case_id="test-case-id",
                base_top_k=30
            )
            
            # For 500 chunks, should retrieve ~35% = 175, but capped at max_top_k (100)
            assert adaptive_k == 100  # Capped at max
    
    def test_adaptive_topk_respects_min(self, db_session):
        """Test that adaptive top_k respects minimum value"""
        # Mock very small chunk count
        with patch.object(chunk_repository, 'count_by_case', return_value=5):
            adaptive_k = rag_retriever._compute_adaptive_top_k(
                db=db_session,
                case_id="test-case-id",
                base_top_k=30,
                min_top_k=20
            )
            
            # Should be clamped to min_top_k
            assert adaptive_k == 20
    
    def test_adaptive_topk_respects_max(self, db_session):
        """Test that adaptive top_k respects maximum value"""
        # Mock very large chunk count
        with patch.object(chunk_repository, 'count_by_case', return_value=1000):
            adaptive_k = rag_retriever._compute_adaptive_top_k(
                db=db_session,
                case_id="test-case-id",
                base_top_k=30,
                max_top_k=100
            )
            
            # Should be clamped to max_top_k
            assert adaptive_k == 100
    
    def test_adaptive_topk_custom_parameters(self, db_session):
        """Test adaptive top_k with custom min/max parameters"""
        # Mock chunk count
        with patch.object(chunk_repository, 'count_by_case', return_value=150):
            adaptive_k = rag_retriever._compute_adaptive_top_k(
                db=db_session,
                case_id="test-case-id",
                base_top_k=25,
                min_top_k=10,
                max_top_k=80
            )
            
            # For 150 chunks (medium), should be ~75 chunks (50%)
            assert adaptive_k == 75
            assert 10 <= adaptive_k <= 80


@pytest.fixture
def db_session():
    """Mock database session"""
    return Mock()
