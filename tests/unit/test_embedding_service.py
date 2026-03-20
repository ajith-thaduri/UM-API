"""Unit tests for EmbeddingService"""

import pytest
from unittest.mock import MagicMock, patch, Mock
from app.services.embedding_service import EmbeddingService


@pytest.fixture
def mock_openai_response():
    """Mock OpenAI embedding response"""
    mock_data = Mock()
    mock_data.embedding = [0.1] * 1536
    mock_response = Mock()
    mock_response.data = [mock_data]
    return mock_response


@pytest.fixture
def mock_client(mock_openai_response):
    """Mock OpenAI client"""
    client = MagicMock()
    
    def create_embeddings(*args, **kwargs):
        # Return correct number of embeddings based on input
        input_texts = kwargs.get('input', [])
        if isinstance(input_texts, str):
            input_texts = [input_texts]
        
        mock_response = Mock()
        mock_response.data = []
        for i in range(len(input_texts)):
            mock_data = Mock()
            mock_data.embedding = [0.1 + i * 0.01] * 1536
            mock_response.data.append(mock_data)
        return mock_response
    
    client.embeddings.create.side_effect = create_embeddings
    return client


@pytest.fixture
def embedding_service(mock_client):
    """EmbeddingService with mock client factory"""
    return EmbeddingService(client_factory=lambda: mock_client)


def test_generate_embedding_success(embedding_service, mock_client):
    """Test successful embedding generation"""
    result = embedding_service.generate_embedding("test text")
    
    assert len(result) == 1536
    assert all(isinstance(x, float) for x in result)
    assert mock_client.embeddings.create.called


def test_generate_embedding_empty_text(embedding_service):
    """Test that empty text raises ValueError"""
    with pytest.raises(ValueError, match="Cannot generate embedding for empty text"):
        embedding_service.generate_embedding("")
    
    with pytest.raises(ValueError, match="Cannot generate embedding for empty text"):
        embedding_service.generate_embedding("   ")


def test_generate_embedding_caching(embedding_service, mock_client):
    """Test that embeddings are cached"""
    # First call - should hit API
    result1 = embedding_service.generate_embedding("cache_test_text")
    
    # Second call with same text - should use cache
    result2 = embedding_service.generate_embedding("cache_test_text")
    
    # Should only call API once
    assert mock_client.embeddings.create.call_count == 1
    assert result1 == result2


def test_generate_embedding_no_cache(embedding_service, mock_client):
    """Test that use_cache=False bypasses cache"""
    # First call
    embedding_service.generate_embedding("no_cache_test", use_cache=False)
    
    # Second call with use_cache=False - should hit API again
    embedding_service.generate_embedding("no_cache_test", use_cache=False)
    
    # Should call API twice
    assert mock_client.embeddings.create.call_count == 2


def test_generate_embeddings_batch(mock_openai_response):
    """Test batch embedding generation"""
    # Create mock responses for different batches
    mock_response1 = MagicMock()
    mock_response1.data = [MagicMock(embedding=[0.1]*1536), MagicMock(embedding=[0.2]*1536)]
    mock_response2 = MagicMock()
    mock_response2.data = [MagicMock(embedding=[0.3]*1536)]
    
    mock_client = MagicMock()
    mock_client.embeddings.create.side_effect = [mock_response1, mock_response2, mock_response1, mock_response2]
    
    service = EmbeddingService(client_factory=lambda: mock_client)
    
    texts = ["batch_text1", "batch_text2", "batch_text3"]
    results = service.generate_embeddings_batch(texts, batch_size=2, use_cache=False)
    
    assert len(results) == 3
    assert all(len(r) == 1536 for r in results)
    assert mock_client.embeddings.create.called


def test_generate_embeddings_batch_empty(embedding_service):
    """Test batch generation with empty list"""
    results = embedding_service.generate_embeddings_batch([])
    assert results == []


def test_generate_embeddings_batch_with_empty_texts(embedding_service, mock_client):
    """Test batch generation with some empty texts"""
    texts = ["batch_empty_text1", "", "batch_empty_text3"]
    results = embedding_service.generate_embeddings_batch(texts, use_cache=False)
    
    assert len(results) == 3
    # Empty text should get zero vector
    assert results[1] == [0.0] * 1536


def test_generate_embeddings_batch_caching(embedding_service, mock_client):
    """Test that batch generation uses cache"""
    # Clear cache to start fresh
    embedding_service.clear_cache()
    
    texts = ["unique_batch_cache_1", "unique_batch_cache_2"]
    
    # First batch - should hit API and populate cache
    embedding_service.generate_embeddings_batch(texts, use_cache=True)
    
    # Cache should now have entries
    assert embedding_service.get_cache_size() == 2
    
    # Second batch with same texts - should use cache (verify by checking cache is still size 2)
    results = embedding_service.generate_embeddings_batch(texts, use_cache=True)
    
    # Should have results and cache size unchanged
    assert len(results) == 2
    assert embedding_service.get_cache_size() == 2


def test_generate_query_embedding(embedding_service, mock_client):
    """Test query embedding generation"""
    result = embedding_service.generate_query_embedding("query text")
    
    assert len(result) == 1536
    # Query embeddings should not use cache
    assert mock_client.embeddings.create.called


def test_clear_cache(embedding_service):
    """Test cache clearing"""
    # Generate and cache
    embedding_service.generate_embedding("clear_cache_test")
    assert embedding_service.get_cache_size() > 0
    
    # Clear cache
    embedding_service.clear_cache()
    assert embedding_service.get_cache_size() == 0


def test_get_cache_size(embedding_service):
    """Test cache size tracking"""
    # Clear any existing cache first
    embedding_service.clear_cache()
    assert embedding_service.get_cache_size() == 0
    
    embedding_service.generate_embedding("size_text1")
    assert embedding_service.get_cache_size() == 1
    
    embedding_service.generate_embedding("size_text2")
    assert embedding_service.get_cache_size() == 2
    
    # Same text shouldn't increase cache size
    embedding_service.generate_embedding("size_text1")
    assert embedding_service.get_cache_size() == 2
