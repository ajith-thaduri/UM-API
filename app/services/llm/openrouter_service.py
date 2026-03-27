"""OpenRouter LLM service for Tier 1 (OSS models). OpenAI-compatible API."""

from typing import Awaitable, Callable, Dict, List, Optional, Tuple
import logging

from app.core.config import settings
from app.services.llm.base_llm_service import BaseLLMService

logger = logging.getLogger(__name__)

try:
    from openai import AsyncOpenAI
    OPENROUTER_AVAILABLE = True
except ImportError:
    AsyncOpenAI = None
    OPENROUTER_AVAILABLE = False


class OpenRouterService(BaseLLMService):
    """OpenRouter (OSS models) for Tier 1 - timeline, extraction, contradictions, upload agent."""

    def __init__(self):
        self.model = getattr(settings, "OPENROUTER_MODEL", None) or getattr(settings, "TIER1_OPENROUTER_MODEL", "meta-llama/llama-3.1-70b-instruct")
        api_key = getattr(settings, "OPENROUTER_API_KEY", None) or getattr(settings, "TIER1_OPENROUTER_API_KEY", "")
        if OPENROUTER_AVAILABLE and api_key:
            self.client = AsyncOpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=api_key,
            )
        else:
            self.client = None

    def is_available(self) -> bool:
        return OPENROUTER_AVAILABLE and self.client is not None and bool(
            getattr(settings, "OPENROUTER_API_KEY", None) or getattr(settings, "TIER1_OPENROUTER_API_KEY", "")
        )

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        system_message: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: int = 4000,
        response_format: Optional[Dict] = None,
        seed: Optional[int] = None,
    ) -> Tuple[str, Dict[str, int]]:
        if not self.client:
            raise ValueError("OpenRouter client not initialized. Set OPENROUTER_API_KEY (or TIER1_OPENROUTER_API_KEY).")
        formatted = []
        if system_message:
            formatted.append({"role": "system", "content": system_message})
        formatted.extend(messages)
        params = {
            "model": self.model,
            "messages": formatted,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format:
            params["response_format"] = response_format
        if seed is not None:
            params["seed"] = seed
        try:
            response = await self.client.chat.completions.create(**params)
            usage = {
                "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                "total_tokens": response.usage.total_tokens if response.usage else 0,
            }
            return (response.choices[0].message.content or "", usage)
        except Exception as e:
            logger.error("OpenRouter API error: %s", e, exc_info=True)
            raise

    async def close(self):
        if self.client:
            try:
                await self.client.close()
            except Exception as e:
                logger.warning("Error closing OpenRouter client: %s", e)

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
        if not self.client:
            raise ValueError("OpenRouter client not initialized. Set OPENROUTER_API_KEY (or TIER1_OPENROUTER_API_KEY).")
        formatted = []
        if system_message:
            formatted.append({"role": "system", "content": system_message})
        formatted.extend(messages)
        params = {
            "model": self.model,
            "messages": formatted,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if response_format:
            params["response_format"] = response_format
        if seed is not None:
            params["seed"] = seed

        text_parts: List[str] = []
        usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        try:
            stream = await self.client.chat.completions.create(**params)
            async for chunk in stream:
                delta = ""
                if chunk.choices and chunk.choices[0].delta:
                    delta = chunk.choices[0].delta.content or ""
                if delta:
                    text_parts.append(delta)
                    if on_token:
                        maybe = on_token(delta)
                        if hasattr(maybe, "__await__"):
                            await maybe
                if getattr(chunk, "usage", None):
                    usage = {
                        "prompt_tokens": chunk.usage.prompt_tokens or 0,
                        "completion_tokens": chunk.usage.completion_tokens or 0,
                        "total_tokens": chunk.usage.total_tokens or 0,
                    }
            return ("".join(text_parts), usage)
        except Exception as e:
            logger.error("OpenRouter API stream error: %s", e, exc_info=True)
            raise
