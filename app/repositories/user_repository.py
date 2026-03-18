"""User repository"""

from typing import Optional, List
from sqlalchemy.orm import Session

from app.repositories.base import BaseRepository
from app.models.user import User, UserRole


class UserRepository(BaseRepository[User]):
    """Repository for User model"""

    def __init__(self):
        super().__init__(User)

    def get_by_email(self, db: Session, email: str) -> Optional[User]:
        """
        Get user by email

        Args:
            db: Database session
            email: User email

        Returns:
            User instance or None
        """
        return db.query(User).filter(User.email == email).first()

    def get_by_role(
        self,
        db: Session,
        role: UserRole,
        skip: int = 0,
        limit: int = 100,
    ) -> List[User]:
        """
        Get users by role

        Args:
            db: Database session
            role: User role
            skip: Number of records to skip
            limit: Maximum number of records

        Returns:
            List of users
        """
        return (
            db.query(User)
            .filter(User.role == role)
            .filter(User.is_active == True)
            .offset(skip)
            .limit(limit)
            .all()
        )

    def get_active_users(
        self, db: Session, skip: int = 0, limit: int = 100
    ) -> List[User]:
        """
        Get all active users

        Args:
            db: Database session
            skip: Number of records to skip
            limit: Maximum number of records

        Returns:
            List of active users
        """
        return (
            db.query(User)
            .filter(User.is_active == True)
            .offset(skip)
            .limit(limit)
            .all()
        )
    
    def get_by_provider(
        self,
        db: Session,
        provider: str,
        provider_user_id: str
    ) -> Optional[User]:
        """
        Get user by OAuth provider and provider user ID
        
        Args:
            db: Database session
            provider: Auth provider string (e.g., 'google' or AuthProvider.GOOGLE.value)
            provider_user_id: Provider's user ID (e.g., Google sub claim)
            
        Returns:
            User instance or None
        """
        # Convert enum to string if needed
        if hasattr(provider, 'value'):
            provider = provider.value
        return db.query(User).filter(
            User.auth_provider == provider,
            User.provider_user_id == provider_user_id
        ).first()

