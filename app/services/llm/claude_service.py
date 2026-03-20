"""Claude LLM service implementation"""

from typing import Dict, List, Optional, Tuple
import logging

try:
    from anthropic import AsyncAnthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    AsyncAnthropic = None

from app.core.config import settings
from app.services.llm.base_llm_service import BaseLLMService

logger = logging.getLogger(__name__)


class ClaudeService(BaseLLMService):
    """Claude (Anthropic) implementation of LLM service (async)"""
    
    def __init__(self):
        if not ANTHROPIC_AVAILABLE:
            logger.warning("anthropic package not installed. Install with: pip install anthropic")
            self.client = None
        else:
            self.client = AsyncAnthropic(api_key=settings.CLAUDE_API_KEY) if settings.CLAUDE_API_KEY else None
        
        self.model = settings.CLAUDE_MODEL
        self.temperature = settings.CLAUDE_TEMPERATURE
        self.max_tokens = settings.CLAUDE_MAX_TOKENS
    
    def is_available(self) -> bool:
        """Check if Claude service is available"""
        return ANTHROPIC_AVAILABLE and self.client is not None and bool(settings.CLAUDE_API_KEY)
    
    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        system_message: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: int = 4000,
        response_format: Optional[Dict] = None,
        seed: Optional[int] = None  # Accepted for interface consistency, but not used (Claude doesn't support seed)
    ) -> Tuple[str, Dict[str, int]]:
        """Generate chat completion using Claude with usage metrics (async)"""
        if not self.client:
            raise ValueError("Claude client not initialized. Check CLAUDE_API_KEY in config.")
        
        # Claude uses a different message format
        # Convert OpenAI format to Claude format
        claude_messages = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            
            # Claude uses "assistant" instead of "system" for assistant messages
            if role == "assistant":
                claude_messages.append({
                    "role": "assistant",
                    "content": content
                })
            elif role == "user":
                claude_messages.append({
                    "role": "user",
                    "content": content
                })
            # System messages are handled separately in Claude API
        
        # Build request parameters
        request_params = {
            "model": self.model,
            "messages": claude_messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        
        # Claude API uses system parameter instead of system message in messages array
        if system_message:
            request_params["system"] = system_message
        
        # Note: Claude doesn't support response_format like OpenAI's json_object
        # If JSON is needed, it should be requested in the prompt
        if response_format:
            logger.warning("Claude API doesn't support response_format parameter. JSON format should be requested in the prompt.")
        
        try:
            response = await self.client.messages.create(**request_params)
            
            # Extract usage metrics from response
            usage = {
                "prompt_tokens": response.usage.input_tokens if response.usage else 0,
                "completion_tokens": response.usage.output_tokens if response.usage else 0,
                "total_tokens": (response.usage.input_tokens + response.usage.output_tokens) if response.usage else 0,
            }
            
            # Claude returns content as a list of TextBlock objects
            # Extract text from all content blocks and join them
            if response.content:
                text_parts = []
                for content_block in response.content:
                    # TextBlock has a 'text' attribute
                    if hasattr(content_block, 'text'):
                        text_parts.append(content_block.text)
                    elif isinstance(content_block, dict) and 'text' in content_block:
                        text_parts.append(content_block['text'])
                    else:
                        text_parts.append(str(content_block))
                return ''.join(text_parts), usage
            return "", usage
        except Exception as e:
            logger.error(f"Claude API error: {e}", exc_info=True)
            raise
    
    async def close(self):
        """Close the async Claude client and cleanup connections"""
        if self.client:
            try:
                # Close the client - this may spawn background tasks
                await self.client.close()
            except Exception as e:
                # Handle httpx connection pool cleanup errors gracefully
                # This can happen when the connection is already closed or during shutdown
                # The error message indicates the transport is already closed, which is fine
                error_str = str(e).lower()
                if any(phrase in error_str for phrase in [
                    "unable to perform operation",
                    "handler is closed",
                    "tcp transport closed",
                    "transport closed"
                ]):
                    # This is a harmless error - the connection is already closed
                    logger.debug(f"Claude client connection already closed (harmless): {type(e).__name__}")
                else:
                    logger.warning(f"Error closing Claude client: {e}")

