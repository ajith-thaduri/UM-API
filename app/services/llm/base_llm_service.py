"""Base LLM service interface"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple


class BaseLLMService(ABC):
    """Abstract base class for LLM providers"""
    
    @abstractmethod
    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        system_message: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: int = 4000,
        response_format: Optional[Dict] = None,
        seed: Optional[int] = None
    ) -> Tuple[str, Dict[str, int]]:
        """
        Generate chat completion with usage metrics (async)
        
        Args:
            messages: List of message dicts with 'role' and 'content' keys
            system_message: Optional system message (will be prepended to messages)
            temperature: Sampling temperature
            max_tokens: Maximum tokens in response
            response_format: Optional response format (e.g., {"type": "json_object"})
            seed: Optional seed for reproducibility (OpenAI only, ignored by Claude)
            
        Returns:
            Tuple of (response_text, usage_dict)
            usage_dict: {"prompt_tokens": int, "completion_tokens": int, "total_tokens": int}
        """
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """Check if the LLM service is available (API key configured)"""
        pass
    
    async def close(self):
        """
        Cleanup method for closing async HTTP clients.
        Should be called during application shutdown.
        """
        pass

