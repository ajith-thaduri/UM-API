"""Embedding service for generating text embeddings"""

import logging
from typing import List, Dict, Optional, Callable
from openai import OpenAI
from concurrent.futures import ThreadPoolExecutor, as_completed

from app.core.config import settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Service for generating text embeddings using OpenAI"""

    def __init__(self, client_factory: Optional[Callable[[], OpenAI]] = None):
        self.client: Optional[OpenAI] = None
        self.model = settings.EMBEDDING_MODEL
        self.dimensions = settings.EMBEDDING_DIMENSIONS
        self._cache: Dict[str, List[float]] = {}
        self._client_factory = client_factory or self._default_client_factory

    def _default_client_factory(self) -> OpenAI:
        """Default factory to create OpenAI client"""
        if not settings.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY is not configured")
        return OpenAI(api_key=settings.OPENAI_API_KEY)

    def _get_client(self) -> OpenAI:
        """Lazily initialize OpenAI client"""
        if self.client is None:
            self.client = self._client_factory()
        return self.client

    def generate_embedding(self, text: str, use_cache: bool = True) -> List[float]:
        """
        Generate embedding for a single text
        
        Args:
            text: Text to embed
            use_cache: Whether to use cached embeddings
            
        Returns:
            List of floats representing the embedding
        """
        if not text or not text.strip():
            raise ValueError("Cannot generate embedding for empty text")
        
        # Clean and truncate text
        text = text.strip()
        
        # Check cache
        cache_key = hash(text)
        if use_cache and cache_key in self._cache:
            return self._cache[cache_key]
        
        try:
            client = self._get_client()
            
            response = client.embeddings.create(
                model=self.model,
                input=text,
                dimensions=self.dimensions
            )
            
            embedding = response.data[0].embedding
            
            # Cache the result
            if use_cache:
                self._cache[cache_key] = embedding
            
            return embedding
            
        except Exception as e:
            logger.error(f"Error generating embedding: {e}")
            raise

    def generate_embeddings_batch(
        self,
        texts: List[str],
        batch_size: int = 100,
        use_cache: bool = True
    ) -> List[List[float]]:
        """
        Generate embeddings for multiple texts in batches
        
        Args:
            texts: List of texts to embed
            batch_size: Number of texts per API call
            use_cache: Whether to use cached embeddings
            
        Returns:
            List of embeddings (same order as input)
        """
        if not texts:
            return []
        
        # Clean texts
        cleaned_texts = [t.strip() for t in texts]
        
        # Check which texts need embedding
        embeddings = [None] * len(cleaned_texts)
        texts_to_embed = []
        indices_to_embed = []
        
        for i, text in enumerate(cleaned_texts):
            if not text:
                embeddings[i] = [0.0] * self.dimensions  # Zero vector for empty text
                continue
                
            cache_key = hash(text)
            if use_cache and cache_key in self._cache:
                embeddings[i] = self._cache[cache_key]
            else:
                texts_to_embed.append(text)
                indices_to_embed.append(i)
        
        # Generate embeddings for texts not in cache
        if texts_to_embed:
            try:
                # Split into batches
                batches = []
                for batch_start in range(0, len(texts_to_embed), batch_size):
                    batch_end = min(batch_start + batch_size, len(texts_to_embed))
                    batch_texts = texts_to_embed[batch_start:batch_end]
                    batch_indices = indices_to_embed[batch_start:batch_end]
                    batches.append((batch_texts, batch_indices, batch_start, batch_end))
                
                # Process batches in parallel (up to 5 concurrent batches)
                # Each thread gets its own client instance for thread safety
                def process_batch_with_client(batch_data):
                    batch_texts, batch_indices, batch_start, batch_end = batch_data
                    try:
                        # Use client factory for thread safety and testability
                        thread_client = self._client_factory()
                        response = thread_client.embeddings.create(
                            model=self.model,
                            input=batch_texts,
                            dimensions=self.dimensions
                        )
                        
                        batch_results = []
                        for j, embedding_data in enumerate(response.data):
                            embedding = embedding_data.embedding
                            original_index = batch_indices[j]
                            
                            # Cache the result (thread-safe dict operations are atomic in CPython)
                            if use_cache:
                                cache_key = hash(batch_texts[j])
                                self._cache[cache_key] = embedding
                            
                            batch_results.append((original_index, embedding))
                        
                        logger.info(f"Generated embeddings for batch {batch_start}-{batch_end}")
                        return batch_results
                    except Exception as e:
                        logger.error(f"Error processing batch {batch_start}-{batch_end}: {e}")
                        raise
                
                with ThreadPoolExecutor(max_workers=5) as executor:
                    futures = {executor.submit(process_batch_with_client, batch): batch for batch in batches}
                    
                    for future in as_completed(futures):
                        try:
                            batch_results = future.result()
                            for original_index, embedding in batch_results:
                                embeddings[original_index] = embedding
                        except Exception as e:
                            logger.error(f"Error getting batch result: {e}")
                            raise
                    
            except Exception as e:
                logger.error(f"Error generating batch embeddings: {e}")
                raise
        
        return embeddings

    def generate_query_embedding(self, query: str) -> List[float]:
        """
        Generate embedding for a search query
        
        This is separate from document embeddings in case we want
        to apply different processing for queries vs documents
        
        Args:
            query: Search query text
            
        Returns:
            Query embedding
        """
        # For now, use the same embedding model
        # Could add query-specific preprocessing here
        return self.generate_embedding(query, use_cache=False)

    def clear_cache(self):
        """Clear the embedding cache"""
        self._cache.clear()
        logger.info("Embedding cache cleared")

    def get_cache_size(self) -> int:
        """Get the number of cached embeddings"""
        return len(self._cache)


# Singleton instance
embedding_service = EmbeddingService()

