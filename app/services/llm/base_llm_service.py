"""Base LLM service interface"""

from abc import ABC, abstractmethod
from typing import Awaitable, Callable, Dict, List, Optional, Tuple


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

    async def chat_completion_stream(
        self,
        messages: List[Dict[str, str]],
        system_message: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: int = 4000,
        response_format: Optional[Dict] = None,
        seed: Optional[int] = None,
        on_token: Optional[Callable[[str], Awaitable[None] | None]] = None,
    ) -> Tuple[str, Dict[str, int]]:
        """
        Optional streaming interface.
        Default behavior falls back to non-stream completion and emits one full chunk.
        """
        text, usage = await self.chat_completion(
            messages=messages,
            system_message=system_message,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,
            seed=seed,
        )
        if on_token and text:
            maybe = on_token(text)
            if hasattr(maybe, "__await__"):
                await maybe
        return text, usage

