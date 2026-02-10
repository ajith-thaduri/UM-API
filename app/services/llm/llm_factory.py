"""LLM service factory for selecting provider based on config or user preferences"""

import logging
from typing import Optional
from sqlalchemy.orm import Session

from app.core.config import settings
from app.services.llm.base_llm_service import BaseLLMService
from app.services.llm.openai_service import OpenAIService
from app.services.llm.claude_service import ClaudeService

logger = logging.getLogger(__name__)


def get_llm_service(provider: Optional[str] = None, model: Optional[str] = None) -> BaseLLMService:
    """
    Get LLM service based on configuration or provided parameters
    
    Args:
        provider: Optional provider override (openai/claude)
        model: Optional model override
    
    Returns:
        BaseLLMService instance (OpenAI or Claude)
        
    Raises:
        ValueError: If provider is not supported or not available
    """
    # Use provided provider or fallback to config
    selected_provider = (provider or settings.LLM_PROVIDER).lower()
    
    if selected_provider == "openai":
        service = OpenAIService()
        # Override model if provided
        if model:
            service.model = model
        if not service.is_available():
            logger.warning("OpenAI service not available. Check OPENAI_API_KEY in config.")
        return service
    
    elif selected_provider == "claude":
        service = ClaudeService()
        # Override model if provided
        if model:
            service.model = model
        if not service.is_available():
            logger.warning("Claude service not available. Check CLAUDE_API_KEY in config and ensure anthropic package is installed.")
        return service
    
    else:
        raise ValueError(
            f"Unsupported LLM provider: {selected_provider}. "
            f"Supported providers: 'openai', 'claude'. "
            f"Set LLM_PROVIDER in config."
        )


def get_llm_service_for_user(
    db: Session,
    user_id: str,
    provider: Optional[str] = None,
    model: Optional[str] = None
) -> BaseLLMService:
    """
    Get LLM service for a specific user, checking user preferences first
    
    Args:
        db: Database session
        user_id: User ID
        provider: Optional provider override (takes precedence over user preference)
        model: Optional model override (takes precedence over user preference)
    
    Returns:
        BaseLLMService instance configured for the user
    """
    # If provider/model are explicitly provided, use them
    if provider and model:
        return get_llm_service(provider, model)
    
    # Check user preferences
    try:
        from app.repositories.user_preference_repository import UserPreferenceRepository
        preference_repo = UserPreferenceRepository()
        preference = preference_repo.get_by_user_id(db, user_id)
        
        if preference:
            # Use user preference, but allow override
            selected_provider = provider or preference.llm_provider
            selected_model = model or preference.llm_model
            logger.debug(f"Using user preference: {selected_provider}/{selected_model} for user {user_id}")
            return get_llm_service(selected_provider, selected_model)
    except Exception as e:
        logger.warning(f"Error loading user preference for user {user_id}: {e}, falling back to global config")
    
    # Fallback to global config
    if provider:
        return get_llm_service(provider, model)
    
    return get_llm_service()


# Singleton instance - lazy initialization with config checking
# Note: This is kept for backward compatibility, but per-user services should use get_llm_service_for_user
_llm_service_instance: BaseLLMService = None
_cached_provider: str = None
_active_services: list = []  # Track all active service instances for cleanup


def get_llm_service_instance() -> BaseLLMService:
    """
    Get singleton LLM service instance based on global config.
    Recreates the service if the provider has changed in config.
    
    Note: For per-user preferences, use get_llm_service_for_user() instead.
    """
    global _llm_service_instance, _cached_provider, _active_services
    current_provider = settings.LLM_PROVIDER.lower()
    
    # Recreate service if provider changed or if not initialized
    if _llm_service_instance is None or _cached_provider != current_provider:
        # Close old instance if it exists
        if _llm_service_instance:
            _active_services.append(_llm_service_instance)
        _llm_service_instance = get_llm_service()
        _cached_provider = current_provider
        logger.info(f"LLM service initialized with provider: {current_provider}")
    
    return _llm_service_instance


async def close_all_llm_services():
    """
    Close all active LLM service clients.
    Should be called during application shutdown.
    """
    global _llm_service_instance, _active_services
    import asyncio
    
    services_to_close = []
    if _llm_service_instance:
        services_to_close.append(_llm_service_instance)
    services_to_close.extend(_active_services)
    
    # Close all services concurrently with error handling
    if services_to_close:
        results = await asyncio.gather(
            *[service.close() for service in services_to_close],
            return_exceptions=True
        )
        # Log any exceptions that occurred during close
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                # RuntimeError about closed connections is expected and harmless
                if isinstance(result, RuntimeError) and ("unable to perform operation" in str(result) or "handler is closed" in str(result)):
                    logger.debug(f"Service {i} connection already closed (expected): {result}")
                else:
                    logger.warning(f"Error closing service {i}: {result}")
        logger.info(f"Closed {len(services_to_close)} LLM service clients")
    
    _llm_service_instance = None
    _active_services.clear()

