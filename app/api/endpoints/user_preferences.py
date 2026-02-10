"""User preferences API endpoints for LLM settings"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Dict, Any
from pydantic import BaseModel

from app.db.session import get_db
from app.db.dependencies import get_user_preference_repository
from app.repositories.user_preference_repository import UserPreferenceRepository
from app.api.endpoints.auth import get_current_user
from app.models.user import User
from app.core.config import settings

router = APIRouter()


class UserPreferenceRequest(BaseModel):
    llm_provider: str  # "openai" or "claude"
    llm_model: str  # Model name


class UserPreferenceResponse(BaseModel):
    llm_provider: str
    llm_model: str
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
            "created_at": "",
            "updated_at": ""
        }
    
    return {
        "llm_provider": preference.llm_provider,
        "llm_model": preference.llm_model,
        "created_at": preference.created_at.isoformat(),
        "updated_at": preference.updated_at.isoformat()
    }


@router.put("/user/preferences", response_model=UserPreferenceResponse)
async def update_user_preferences(
    request: UserPreferenceRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    preference_repository: UserPreferenceRepository = Depends(get_user_preference_repository),
):
    """Update user's LLM preferences"""
    # Validate provider
    if request.llm_provider.lower() not in ["openai", "claude"]:
        raise HTTPException(status_code=400, detail="Invalid provider. Must be 'openai' or 'claude'")
    
    # Validate model (basic check - could be enhanced)
    if not request.llm_model or len(request.llm_model.strip()) == 0:
        raise HTTPException(status_code=400, detail="Model name is required")
    
    # Update or create preference
    preference = preference_repository.upsert(
        db=db,
        user_id=current_user.id,
        llm_provider=request.llm_provider.lower(),
        llm_model=request.llm_model
    )
    
    return {
        "llm_provider": preference.llm_provider,
        "llm_model": preference.llm_model,
        "created_at": preference.created_at.isoformat(),
        "updated_at": preference.updated_at.isoformat()
    }


@router.get("/user/preferences/models", response_model=AvailableModelsResponse)
async def get_available_models(
    provider: str,
    current_user: User = Depends(get_current_user),
):
    """Get available models for a provider"""
    provider_lower = provider.lower()
    
    if provider_lower == "openai":
        models = [
            {
                "name": "gpt-4o",
                "display_name": "GPT-4o",
                "description": "Latest GPT-4 optimized model - best quality and speed"
            },
            {
                "name": "gpt-4o-mini",
                "display_name": "GPT-4o Mini",
                "description": "Faster and more cost-effective GPT-4 variant"
            },
            {
                "name": "gpt-4-turbo",
                "display_name": "GPT-4 Turbo",
                "description": "Previous generation GPT-4 with extended context"
            },
            {
                "name": "gpt-3.5-turbo",
                "display_name": "GPT-3.5 Turbo",
                "description": "Fast and cost-effective for simpler tasks"
            }
        ]
    elif provider_lower == "claude":
        models = [
            {
                "name": "claude-sonnet-4-5-20250929",
                "display_name": "Claude Sonnet 4.5",
                "description": "Latest Sonnet 4.5 - highest quality, recommended"
            },
            {
                "name": "claude-sonnet-4-5",
                "display_name": "Claude Sonnet 4.5 (latest)",
                "description": "Latest Sonnet 4.5 without date suffix"
            },
            {
                "name": "claude-haiku-4-5",
                "display_name": "Claude Haiku 4.5",
                "description": "Fast and cost-effective Haiku model"
            },
            {
                "name": "claude-3-5-haiku-20241022",
                "display_name": "Claude 3.5 Haiku",
                "description": "Previous generation Haiku model"
            },
            {
                "name": "claude-3-haiku-20240307",
                "display_name": "Claude 3 Haiku",
                "description": "Older Haiku model"
            }
        ]
    else:
        raise HTTPException(status_code=400, detail="Invalid provider. Must be 'openai' or 'claude'")
    
    return {
        "provider": provider_lower,
        "models": models
    }

