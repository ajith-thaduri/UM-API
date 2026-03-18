"""User schemas"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field
from enum import Enum


class UserRole(str, Enum):
    """User role enumeration"""

    UM_NURSE = "um_nurse"
    MEDICAL_DIRECTOR = "medical_director"
    ADMIN = "admin"
    AUDITOR = "auditor"


class UserCreate(BaseModel):
    """Schema for creating a new user"""

    email: EmailStr
    name: str
    password: Optional[str] = None
    role: UserRole = Field(default=UserRole.UM_NURSE)


class UserResponse(BaseModel):
    """Schema for user response"""

    id: str
    email: str
    name: str
    role: UserRole
    is_active: bool
    created_at: datetime
    last_login: Optional[datetime] = None
    auth_provider: Optional[str] = None
    avatar_url: Optional[str] = None
    email_verified: Optional[bool] = None

    class Config:
        from_attributes = True


class UserProfileUpdate(BaseModel):
    """Schema for updating user profile"""
    
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    # Note: Email and avatar_url cannot be updated for OAuth users
    # They are managed by the OAuth provider

