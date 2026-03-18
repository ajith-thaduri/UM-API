"""Users API endpoints"""

from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.dependencies import get_user_repository
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserCreate, UserResponse, UserProfileUpdate
from app.models.user import User, AuthProvider
from app.api.endpoints.auth import get_current_user

router = APIRouter()


@router.get("/", response_model=List[UserResponse])
async def get_users(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    user_repository: UserRepository = Depends(get_user_repository),
):
    """Get all users with pagination"""
    users = user_repository.get_all(db, skip=skip, limit=limit)
    return users


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: str,
    db: Session = Depends(get_db),
    user_repository: UserRepository = Depends(get_user_repository),
):
    """Get a specific user by ID"""
    user = user_repository.get_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.post("/", response_model=UserResponse)
async def create_user(
    user: UserCreate,
    db: Session = Depends(get_db),
    user_repository: UserRepository = Depends(get_user_repository),
):
    """Create a new user"""
    import uuid
    from datetime import datetime

    # Check if user already exists
    existing_user = user_repository.get_by_email(db, user.email)
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    # Create new user
    new_user = User(
        id=str(uuid.uuid4()),
        email=user.email,
        name=user.name,
        role=user.role,
        is_active=True,
        created_at=datetime.utcnow(),
        # TODO: Hash password if provided
    )

    return user_repository.create(db, new_user)


@router.put("/me", response_model=UserResponse)
async def update_current_user_profile(
    profile_data: UserProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    user_repository: UserRepository = Depends(get_user_repository),
):
    """Update current user's profile
    
    For OAuth users (Google), only name can be updated.
    Email and avatar are managed by the OAuth provider.
    """
    # Update name if provided
    if profile_data.name is not None:
        current_user.name = profile_data.name
    
    # For OAuth users, prevent email/avatar updates
    # (These are managed by the OAuth provider)
    is_oauth_user = (
        current_user.auth_provider and 
        current_user.auth_provider.lower() == AuthProvider.GOOGLE.value.lower()
    )
    
    if is_oauth_user:
        # OAuth users can only update their name
        # Email and avatar come from Google
        pass
    # Password users can update more fields in the future
    
    db.commit()
    db.refresh(current_user)
    
    return current_user

