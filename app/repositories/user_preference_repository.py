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

    def upsert(
        self, 
        db: Session, 
        user_id: str, 
        llm_provider: str, 
        llm_model: str, 
        presidio_enabled: Optional[bool] = None,
        tier1_model: Optional[str] = None,
        tier2_model: Optional[str] = None
    ) -> UserPreference:
        """
        Create or update user preference

        Args:
            db: Database session
            user_id: User ID
            llm_provider: LLM provider (openai/claude)
            llm_model: LLM model name
            presidio_enabled: Whether Presidio is enabled for this user
            tier1_model: OpenRouter model for Tier 1
            tier2_model: Claude model for Tier 2
            
        Returns:
            UserPreference instance
        """
        preference = self.get_by_user_id(db, user_id)
        
        if preference:
            preference.llm_provider = llm_provider
            preference.llm_model = llm_model
            if presidio_enabled is not None:
                preference.presidio_enabled = presidio_enabled
            if tier1_model is not None:
                preference.tier1_model = tier1_model
            if tier2_model is not None:
                preference.tier2_model = tier2_model
            return self.update(db, preference)
        else:
            import uuid
            from datetime import datetime
            preference = UserPreference(
                id=str(uuid.uuid4()),
                user_id=user_id,
                llm_provider=llm_provider,
                llm_model=llm_model,
                presidio_enabled=presidio_enabled if presidio_enabled is not None else True,
                tier1_model=tier1_model,
                tier2_model=tier2_model,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            return self.create(db, preference)

