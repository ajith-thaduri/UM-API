import uuid
from sqlalchemy import Column, String, Boolean, JSON, DateTime
from sqlalchemy.sql import func
from app.db.session import Base

class PresidioEngine(Base):
    """
    Model for managing NER engines/models available to Presidio.
    Allows dynamic selection and configuration of models from the database.
    """
    __tablename__ = "presidio_engines"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False, unique=True, index=True)
    description = Column(String, nullable=True)
    
    # Engine type: 'spacy', 'transformers', etc.
    engine_type = Column(String, nullable=False)
    
    # Model name/path: 'en_core_web_lg', 'obi/deid_roberta_i2b2', etc.
    model_name = Column(String, nullable=False)
    
    # Whether this model is the currently active one
    is_active = Column(Boolean, default=False, nullable=False)
    
    # Optional JSON configuration (e.g., confidence thresholds, specific labels)
    config = Column(JSON, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<PresidioEngine(name={self.name}, type={self.engine_type}, active={self.is_active})>"
