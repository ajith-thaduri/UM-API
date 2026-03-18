"""Authentication endpoints"""

import uuid
import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.dependencies import get_user_repository
from app.repositories.user_repository import UserRepository
from app.models.user import User, UserRole
from app.schemas.auth import LoginRequest, TokenResponse, RegisterRequest, RefreshTokenRequest
from app.services.auth_service import (
    authenticate_user,
    get_password_hash,
    create_access_token,
    get_user_from_token,
    blacklist_token,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])
security = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    """Dependency to get current authenticated user"""
    token = credentials.credentials
    user = get_user_from_token(token, db)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


@router.post("/login", response_model=TokenResponse)
async def login(
    login_data: LoginRequest,
    db: Session = Depends(get_db),
):
    """Login endpoint - returns JWT token"""
    user = authenticate_user(db, login_data.email, login_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token = create_access_token(data={"sub": user.id})
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user_id=user.id,
        email=user.email,
        name=user.name,
    )


@router.post("/register", response_model=TokenResponse)
async def register(
    register_data: RegisterRequest,
    db: Session = Depends(get_db),
    user_repository: UserRepository = Depends(get_user_repository),
):
    """Register a new user"""
    # Check if user already exists
    existing_user = user_repository.get_by_email(db, register_data.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Create new user
    new_user = User(
        id=str(uuid.uuid4()),
        email=register_data.email,
        name=register_data.name,
        hashed_password=get_password_hash(register_data.password),
        role="um_nurse",  # Single role as specified
        is_active=True,
        created_at=datetime.utcnow(),
    )
    
    user = user_repository.create(db, new_user)
    
    # Return token for immediate login
    access_token = create_access_token(data={"sub": user.id})
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user_id=user.id,
        email=user.email,
        name=user.name,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    refresh_data: RefreshTokenRequest,
    db: Session = Depends(get_db),
):
    """Refresh access token - allows refreshing even if token is expired"""
    token = refresh_data.token
    # Allow expired tokens for refresh
    user = get_user_from_token(token, db, allow_expired=True)
    
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Create new token
    access_token = create_access_token(data={"sub": user.id})
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user_id=user.id,
        email=user.email,
        name=user.name,
    )


@router.post("/logout")
async def logout(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
):
    """Logout endpoint - invalidates the current token"""
    token = credentials.credentials
    
    # Blacklist the token
    success = blacklist_token(token, db)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid token",
        )
    
    return {"message": "Successfully logged out"}


@router.get("/me")
async def get_current_user_info(
    current_user: User = Depends(get_current_user),
):
    """Get current user information including OAuth data"""
    return {
        "id": current_user.id,
        "email": current_user.email,
        "name": current_user.name,
        "role": current_user.role,
        "is_active": current_user.is_active,
        "auth_provider": current_user.auth_provider or "password",
        "avatar_url": current_user.avatar_url,
        "email_verified": current_user.email_verified or False,
        "created_at": current_user.created_at.isoformat() if current_user.created_at else None,
        "last_login": current_user.last_login.isoformat() if current_user.last_login else None,
    }

