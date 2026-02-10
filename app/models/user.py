"""User model"""

from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Enum, Boolean, JSON, Text, Index
from sqlalchemy.orm import relationship
import enum

from app.db.session import Base


class UserRole(str, enum.Enum):
    """User role enumeration"""

    UM_NURSE = "um_nurse"
    MEDICAL_DIRECTOR = "medical_director"
    ADMIN = "admin"
    AUDITOR = "auditor"


class AuthProvider(str, enum.Enum):
    """Authentication provider enumeration"""
    PASSWORD = "password"
    GOOGLE = "google"
    # Future: MICROSOFT = "microsoft", APPLE = "apple"


class User(Base):
    """User model"""

    __tablename__ = "users"

    id = Column(String, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    hashed_password = Column(String, nullable=True)  # Nullable for SSO users
    
    # OAuth fields
    # Using String instead of Enum to avoid PostgreSQL enum type conflicts
    # Values are validated in application code using AuthProvider enum
    auth_provider = Column(
        String(50),
        default=AuthProvider.PASSWORD.value,  # Use .value to get the string
        nullable=True
    )
    provider_user_id = Column(String(255), nullable=True)  # Google sub claim
    provider_email = Column(String(255), nullable=True)  # Email from provider
    avatar_url = Column(String(500), nullable=True)  # Profile picture URL
    email_verified = Column(Boolean, default=False, nullable=True)
    
    # OAuth tokens (encrypted in application layer)
    oauth_access_token = Column(Text, nullable=True)
    oauth_refresh_token = Column(Text, nullable=True)
    provider_data = Column(JSON, nullable=True)  # Additional provider-specific data
    
    role = Column(
        Enum(
            "um_nurse", "medical_director", "admin", "auditor",
            "UM_NURSE", "MEDICAL_DIRECTOR", "ADMIN", "AUDITOR",
            name="userrole",
            native_enum=False,
            length=30
        ),
        default="um_nurse",
        nullable=False
    )
    is_active = Column(Boolean, default=True, nullable=False)
    
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    last_login = Column(DateTime(timezone=True), nullable=True)
    
    # Performance indexes
    __table_args__ = (
        Index('idx_users_provider_user_id', 'auth_provider', 'provider_user_id'),
        Index('idx_users_provider_email', 'provider_email'),
    )
    
    # Relationships
    cases = relationship("Case", foreign_keys="Case.user_id", back_populates="user")

    def __repr__(self):
        return f"<User {self.email} - {self.role} ({self.auth_provider.value if self.auth_provider else 'password'})>"
