"""Usage metrics model for tracking LLM token usage"""

from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Numeric, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.db.session import Base


class UsageMetrics(Base):
    """Usage metrics model for tracking LLM token usage and costs"""

    __tablename__ = "usage_metrics"

    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    case_id = Column(String, ForeignKey("cases.id", ondelete="SET NULL"), nullable=True, index=True)
    
    # Provider and model information
    provider = Column(String, nullable=False, index=True)  # "openai" or "claude"
    model = Column(String, nullable=False, index=True)  # Model name
    
    # Operation type (e.g., "extraction", "timeline", "summary", "rag", "red_flags")
    operation_type = Column(String, nullable=False, index=True)
    
    # Token usage
    prompt_tokens = Column(Integer, nullable=False, default=0)
    completion_tokens = Column(Integer, nullable=False, default=0)
    total_tokens = Column(Integer, nullable=False, default=0)
    
    # Cost tracking (optional, for future Stripe integration)
    estimated_cost_usd = Column(Numeric(10, 6), nullable=True)  # Up to 9999.999999 USD
    
    # Timestamp
    request_timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    
    # Additional metadata (JSONB for flexibility)
    extra_metadata = Column(JSONB, nullable=True)  # Additional context (e.g., case_number, file_count, etc.)
    
    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    case = relationship("Case", foreign_keys=[case_id])

    # Composite indexes for common queries
    __table_args__ = (
        Index('idx_user_timestamp', 'user_id', 'request_timestamp'),
        Index('idx_provider_model', 'provider', 'model'),
        Index('idx_case_operation', 'case_id', 'operation_type'),
        Index('idx_usage_metadata', 'extra_metadata', postgresql_using='gin'),  # For fast JSON filtering
    )

    def __repr__(self):
        return f"<UsageMetrics {self.id} - {self.provider}/{self.model} - {self.total_tokens} tokens>"

