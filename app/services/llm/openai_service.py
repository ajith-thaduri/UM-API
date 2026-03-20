"""OpenAI LLM service implementation"""

from typing import Dict, List, Optional, Tuple
from openai import AsyncOpenAI
import logging

from app.core.config import settings
from app.services.llm.base_llm_service import BaseLLMService

logger = logging.getLogger(__name__)


class OpenAIService(BaseLLMService):
    """OpenAI implementation of LLM service (async)"""
    
    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY) if settings.OPENAI_API_KEY else None
        self.model = settings.OPENAI_MODEL
        self.temperature = settings.OPENAI_TEMPERATURE
        self.max_tokens = settings.OPENAI_MAX_TOKENS
    
    def is_available(self) -> bool:
        """Check if OpenAI service is available"""
        return self.client is not None and bool(settings.OPENAI_API_KEY)
    
    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        system_message: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: int = 4000,
        response_format: Optional[Dict] = None,
        seed: Optional[int] = None
    ) -> Tuple[str, Dict[str, int]]:
        """Generate chat completion using OpenAI with usage metrics (async)"""
        if not self.client:
            raise ValueError("OpenAI client not initialized. Check OPENAI_API_KEY in config.")
        
        # Prepare messages
        formatted_messages = []
        if system_message:
            formatted_messages.append({
                "role": "system",
                "content": system_message
            })
        formatted_messages.extend(messages)
        
        # Build request parameters
        request_params = {
            "model": self.model,
            "messages": formatted_messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        
        # Add response format if specified
        if response_format:
            request_params["response_format"] = response_format
        
        # Add seed for reproducibility (OpenAI beta feature)
        if seed is not None:
            request_params["seed"] = seed
        
        try:
            response = await self.client.chat.completions.create(**request_params)
            
            # Extract usage metrics from response
            usage = {
                "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                "total_tokens": response.usage.total_tokens if response.usage else 0,
            }
            
            return response.choices[0].message.content, usage
        except Exception as e:
            logger.error(f"OpenAI API error: {e}", exc_info=True)
            raise
    
    async def close(self):
        """Close the async OpenAI client and cleanup connections"""
        if self.client:
            try:
                await self.client.close()
            except Exception as e:
                logger.warning(f"Error closing OpenAI client: {e}")

