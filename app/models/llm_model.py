"""LLM Model definition for dynamic model selection"""

from sqlalchemy import Column, String, Boolean, Integer, DateTime
from sqlalchemy.sql import func
from app.db.session import Base
import uuid

class LLMModel(Base):
    """
    Registry of available LLM models for Tier 1 (Clinical Reasoning).
    Strictly for OpenRouter models or future OSS endpoints.
    """
    __tablename__ = "llm_models"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    
    # Core Identity
    provider = Column(String, nullable=False, default="openrouter") # e.g. "openrouter"
    model_id = Column(String, nullable=False, unique=True, index=True) # e.g. "meta-llama/llama-3.1-70b-instruct"
    
    # Display & Metadata
    display_name = Column(String, nullable=False) # e.g. "Llama 3.1 70B (Recommended)"
    description = Column(String, nullable=True)   # e.g. "Powerful open-source model optimized for medical reasoning"
    context_window = Column(Integer, default=128000)
    
    # Configuration
    is_active = Column(Boolean, default=True)   # Soft delete / Hide from UI
    is_custom = Column(Boolean, default=False)  # True if added by user manually (future scope)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<LLMModel {self.display_name} ({self.model_id})>"
