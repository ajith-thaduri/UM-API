"""User preference repository"""

from typing import Optional
from sqlalchemy.orm import Session

from app.repositories.base import BaseRepository
from app.models.user_preference import UserPreference


class UserPreferenceRepository(BaseRepository[UserPreference]):
    """Repository for UserPreference model"""

    def __init__(self):
        super().__init__(UserPreference)

    def get_by_user_id(self, db: Session, user_id: str) -> Optional[UserPreference]:
        """
        Get user preference by user ID

        Args:
            db: Database session
            user_id: User ID

        Returns:
            UserPreference instance or None if not found
        """
        return db.query(UserPreference).filter(UserPreference.user_id == user_id).first()

    def upsert(self, db: Session, user_id: str, llm_provider: str, llm_model: str) -> UserPreference:
        """
        Create or update user preference

        Args:
            db: Database session
            user_id: User ID
            llm_provider: LLM provider (openai/claude)
            llm_model: LLM model name

        Returns:
            UserPreference instance
        """
        preference = self.get_by_user_id(db, user_id)
        
        if preference:
            preference.llm_provider = llm_provider
            preference.llm_model = llm_model
            return self.update(db, preference)
        else:
            import uuid
            from datetime import datetime
            preference = UserPreference(
                id=str(uuid.uuid4()),
                user_id=user_id,
                llm_provider=llm_provider,
                llm_model=llm_model,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            return self.create(db, preference)

