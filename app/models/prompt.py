"""Prompt models for database-driven prompt management with versioning"""

import enum
from datetime import datetime, timezone
from typing import List, Optional
import uuid

from sqlalchemy import Column, String, Text, DateTime, Boolean, ForeignKey, Integer, JSON, Index
from sqlalchemy.orm import relationship

from app.db.session import Base


class Prompt(Base):
    """
    Core prompt model representing a specific AI prompt.
    """
    __tablename__ = "prompts"

    id = Column(String, primary_key=True, index=True)  # e.g., "medications_extraction"
    category = Column(String, nullable=False, index=True)  # e.g., "clinical_extraction"
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    template = Column(Text, nullable=False)
    system_message = Column(Text, nullable=True)
    variables = Column(JSON, nullable=False)  # List of strings: ["context", "patient_name"]
    is_active = Column(Boolean, default=True, nullable=False)
    
    updated_by = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    def __repr__(self):
        return f"<Prompt {self.id} - {self.name}>"
