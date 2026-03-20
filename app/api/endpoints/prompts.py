"""Prompts API endpoints for managing prompts in the database"""

import logging
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.db.session import get_db
from app.api.endpoints.auth import get_current_user
from app.models.user import User
from app.repositories.prompt_repository import prompt_repository
from app.services.prompt_service import prompt_service

logger = logging.getLogger(__name__)

router = APIRouter(redirect_slashes=False)


# Request/Response Schemas
class PromptResponse(BaseModel):
    id: str
    category: str
    name: str
    description: Optional[str]
    template: str
    system_message: Optional[str]
    variables: List[str]
    is_active: bool
    created_at: str
    updated_at: str
    updated_by: Optional[str]

    class Config:
        from_attributes = True


class PromptUpdateRequest(BaseModel):
    template: str
    system_message: Optional[str] = None
    change_notes: Optional[str] = None


class PromptVersionResponse(BaseModel):
    version_number: int
    event_type: str
    template: str
    system_message: Optional[str]
    changed_by: Optional[str]
    changed_by_email: Optional[str]
    created_at: str
    changes: Optional[Dict[str, Any]]

    class Config:
        from_attributes = True

class PromptActivityResponse(BaseModel):
    id: str
    prompt_id: str
    prompt_name: Optional[str]
    event_type: str
    changed_by_email: Optional[str]
    created_at: str
    change_notes: Optional[str]

    class Config:
        from_attributes = True


@router.get("/prompts", response_model=List[PromptResponse])
async def list_prompts(
    category: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List all prompts, optionally filtered by category"""
    try:
        if category:
            prompts = prompt_repository.get_by_category(db, category)
        else:
            prompts = prompt_repository.get_all(db, filters={"is_active": True})
        
        return [
            PromptResponse(
                id=p.id,
                category=p.category,
                name=p.name,
                description=p.description,
                template=p.template,
                system_message=p.system_message,
                variables=p.variables if isinstance(p.variables, list) else [],
                is_active=p.is_active,
                created_at=p.created_at.isoformat() if p.created_at else "",
                updated_at=p.updated_at.isoformat() if p.updated_at else "",
                updated_by=p.updated_by
            )
            for p in prompts if p.is_active
        ]
    except Exception as e:
        logger.error(f"Error listing prompts: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list prompts"
        )


@router.get("/prompts/activity", response_model=List[PromptActivityResponse])
async def get_all_prompt_activity(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get global activity log for all prompts"""
    from app.models.version_history import VersionHistory
    from app.models.user import User
    from app.models.prompt import Prompt
    
    # Query all history for prompts table
    history = db.query(VersionHistory).filter(
        VersionHistory.referenceable_table_name == "prompts"
    ).order_by(VersionHistory.created_at.desc()).offset(skip).limit(limit).all()
    
    # Get user details
    user_ids = set(h.changed_by_user_id for h in history if h.changed_by_user_id)
    user_map = {}
    if user_ids:
        users = db.query(User).filter(User.id.in_(user_ids)).all()
        user_map = {u.id: u.email for u in users}
        
    # Get prompt names
    prompt_ids = set(h.referenceable_id for h in history)
    prompt_map = {}
    if prompt_ids:
        prompts = db.query(Prompt).filter(Prompt.id.in_(prompt_ids)).all()
        prompt_map = {p.id: p.name for p in prompts}
    
    return [
        PromptActivityResponse(
            id=h.id,
            prompt_id=h.referenceable_id,
            prompt_name=prompt_map.get(h.referenceable_id),
            event_type=h.event_type,
            changed_by_email=user_map.get(h.changed_by_user_id),
            created_at=h.created_at.isoformat(),
            change_notes=h.object_changes.get("change_notes") if h.object_changes else None
        )
        for h in history
    ]


@router.get("/prompts/{prompt_id}", response_model=PromptResponse)
async def get_prompt(
    prompt_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a specific prompt by ID"""
    try:
        prompt = prompt_repository.get_by_id(db, prompt_id)
        if not prompt:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Prompt {prompt_id} not found"
            )
        
        return PromptResponse(
            id=prompt.id,
            category=prompt.category,
            name=prompt.name,
            description=prompt.description,
            template=prompt.template,
            system_message=prompt.system_message,
            variables=prompt.variables if isinstance(prompt.variables, list) else [],
            is_active=prompt.is_active,
            created_at=prompt.created_at.isoformat() if prompt.created_at else "",
            updated_at=prompt.updated_at.isoformat() if prompt.updated_at else "",
            updated_by=prompt.updated_by
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting prompt {prompt_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get prompt"
        )


@router.put("/prompts/{prompt_id}")
async def update_prompt(
    prompt_id: str,
    request: PromptUpdateRequest,
    req: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update a prompt and record history"""
    try:
        # Use request ID for correlation if available
        request_id = req.headers.get("X-Request-ID")
        
        prompt = prompt_repository.update_prompt(
            db=db,
            prompt_id=prompt_id,
            template=request.template,
            system_message=request.system_message,
            user_id=current_user.id,
            change_notes=request.change_notes,
            request_id=request_id
        )
        
        if not prompt:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Prompt {prompt_id} not found"
            )
        
        # Refresh cache
        prompt_service.refresh_cache()
        
        return {
            "success": True,
            "prompt_id": prompt_id,
            "message": "Prompt updated successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating prompt {prompt_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update prompt"
        )


@router.get("/prompts/{prompt_id}/versions", response_model=List[PromptVersionResponse])
async def get_prompt_versions(
    prompt_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get version history for a specific prompt"""
    try:
        history = prompt_repository.get_prompt_history(db, prompt_id)
        
        return [
            PromptVersionResponse(
                version_number=h["version_number"],
                event_type=h["event_type"],
                template=h["snapshot"].get("template", "") if h["snapshot"] else "",
                system_message=h["snapshot"].get("system_message") if h["snapshot"] else None,
                changed_by=h["changed_by"],
                changed_by_email=h.get("changed_by_email"),
                created_at=h["created_at"].isoformat() if h["created_at"] else "",
                changes=h["changes"]
            )
            for h in history
        ]
    except Exception as e:
        logger.error(f"Error getting versions for prompt {prompt_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get prompt versions"
        )


@router.post("/prompts/{prompt_id}/versions/{version_number}/rollback")
async def rollback_prompt(
    prompt_id: str,
    version_number: int,
    req: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Rollback a prompt to a specific historical version"""
    try:
        request_id = req.headers.get("X-Request-ID")
        
        prompt = prompt_repository.rollback_to_version(
            db=db,
            prompt_id=prompt_id,
            version_number=version_number,
            user_id=current_user.id,
            request_id=request_id
        )
        
        if not prompt:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Prompt {prompt_id} or version {version_number} not found"
            )
        
        # Refresh cache
        prompt_service.refresh_cache()
        
        return {
            "success": True,
            "prompt_id": prompt_id,
            "message": f"Rolled back to version {version_number}"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error rolling back prompt {prompt_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to rollback prompt"
        )
