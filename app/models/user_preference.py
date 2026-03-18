"""User preference model for LLM settings"""

from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, ForeignKey, UniqueConstraint, Boolean
from sqlalchemy.orm import relationship

from app.db.session import Base


class UserPreference(Base):
    """User preference model for LLM provider and model selection"""

    __tablename__ = "user_preferences"

    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True, unique=True)
    
    # LLM preferences
    llm_provider = Column(String, nullable=False)  # "openai" or "claude"
    llm_model = Column(String, nullable=False)  # Model name (e.g., "gpt-4o", "claude-sonnet-4-5-20250929")
    tier1_model = Column(String, nullable=True) # OpenRouter model name
    tier2_model = Column(String, nullable=True) # Claude model name
    presidio_enabled = Column(Boolean, default=True, nullable=False)
    
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    
    # Relationships
    user = relationship("User", foreign_keys=[user_id])

    def __repr__(self):
        return f"<UserPreference {self.user_id} - {self.llm_provider}/{self.llm_model}>"
