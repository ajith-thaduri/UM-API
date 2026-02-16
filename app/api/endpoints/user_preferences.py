"""User preferences API endpoints for LLM settings"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Dict, Any, Optional
from pydantic import BaseModel

from app.db.session import get_db
from app.db.dependencies import get_user_preference_repository, get_llm_model_repository
from app.repositories.user_preference_repository import UserPreferenceRepository
from app.repositories.llm_model_repository import LLMModelRepository
from app.api.endpoints.auth import get_current_user
from app.models.user import User
from app.core.config import settings

router = APIRouter()


class UserPreferenceRequest(BaseModel):
    # Tier 1 Config (OSS / OpenRouter)
    tier1_model: str 
    
    # Privacy
    presidio_enabled: Optional[bool] = True

    # Legacy fields (kept for backward compatibility but enforced by backend)
    # The frontend might still send these, but backend will override
    llm_provider: Optional[str] = "openrouter" 
    llm_model: Optional[str] = "claude-sonnet-4-5-20250929"
    tier2_model: Optional[str] = "claude-sonnet-4-5-20250929"


class UserPreferenceResponse(BaseModel):
    llm_provider: str
    llm_model: str
    tier1_model: Optional[str]
    tier2_model: Optional[str]
    presidio_enabled: bool
    created_at: str
    updated_at: str


class AvailableModelsResponse(BaseModel):
    provider: str
    models: list[Dict[str, Any]]  # List of {name, display_name, description}


@router.get("/user/preferences", response_model=UserPreferenceResponse)
async def get_user_preferences(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    preference_repository: UserPreferenceRepository = Depends(get_user_preference_repository),
):
    """Get user's LLM preferences"""
    preference = preference_repository.get_by_user_id(db, current_user.id)
    
    if not preference:
        # Return default from global config
        return {
            "llm_provider": settings.LLM_PROVIDER.lower(),
            "llm_model": settings.OPENAI_MODEL if settings.LLM_PROVIDER.lower() == "openai" else settings.CLAUDE_MODEL,
            "tier1_model": getattr(settings, "TIER1_OPENROUTER_MODEL", "meta-llama/llama-3.1-70b-instruct"),
            "tier2_model": settings.CLAUDE_MODEL,
            "presidio_enabled": True,
            "created_at": "",
            "updated_at": ""
        }
    
    return {
        "llm_provider": preference.llm_provider,
        "llm_model": preference.llm_model,
        "tier1_model": preference.tier1_model,
        "tier2_model": preference.tier2_model,
        "presidio_enabled": preference.presidio_enabled,
        "created_at": preference.created_at.isoformat(),
        "updated_at": preference.updated_at.isoformat()
    }


@router.put("/user/preferences", response_model=UserPreferenceResponse)
async def update_user_preferences(
    request: UserPreferenceRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    preference_repository: UserPreferenceRepository = Depends(get_user_preference_repository),
    model_repository: LLMModelRepository = Depends(get_llm_model_repository),
):
    """Update user's LLM preferences"""
    
    # 1. Enforce Tier 2 Lock (The Vault)
    # Regardless of what user requested, Tier 2 is compliance-locked to Claude
    tier2_model_locked = "claude-sonnet-4-5-20250929"
    
    # 2. Validate Tier 1 Model (The Engine)
    # Check if model exists in our DB or needs to be added (custom)
    accepted_tier1 = request.tier1_model
    existing_model = model_repository.get_by_model_id(db, accepted_tier1)
    
    if not existing_model and accepted_tier1:
        # If it's a custom model string entered by user, we register it as custom
        # In a real prod environment, you might want to ping OpenRouter API to validate it valid first
        model_repository.create(
            db=db,
            model_id=accepted_tier1,
            display_name=accepted_tier1, # Use ID as name for custom
            provider="openrouter",
            is_custom=True
        )

    # Update or create preference
    preference = preference_repository.upsert(
        db=db,
        user_id=current_user.id,
        llm_provider="openrouter", # Logical provider for user operations
        llm_model=tier2_model_locked, # Default model logic
        presidio_enabled=request.presidio_enabled if request.presidio_enabled is not None else True,
        tier1_model=accepted_tier1,
        tier2_model=tier2_model_locked
    )
    
    return {
        "llm_provider": preference.llm_provider,
        "llm_model": preference.llm_model,
        "tier1_model": preference.tier1_model,
        "tier2_model": preference.tier2_model,
        "presidio_enabled": preference.presidio_enabled,
        "created_at": preference.created_at.isoformat(),
        "updated_at": preference.updated_at.isoformat()
    }


@router.get("/llm/tier1-options", response_model=AvailableModelsResponse)
async def get_tier1_options(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    model_repository: LLMModelRepository = Depends(get_llm_model_repository),
):
    """Get active Tier 1 (OpenRouter) models from database"""
    models = model_repository.get_all_active(db, provider="openrouter")
    
    model_list = [
        {
            "name": m.model_id,
            "display_name": m.display_name,
            "description": m.description,
            "is_custom": m.is_custom
        } for m in models
    ]
    
    return {
        "provider": "openrouter",
        "models": model_list
    }

