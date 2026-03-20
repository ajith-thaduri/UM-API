"""Token blacklist model for invalidating JWT tokens on logout"""

from datetime import datetime
from sqlalchemy import Column, String, DateTime, Index
from sqlalchemy.orm import declarative_base

from app.db.session import Base


class TokenBlacklist(Base):
    """Token blacklist model for storing invalidated JWT tokens"""

    __tablename__ = "token_blacklist"

    id = Column(String, primary_key=True, index=True)
    token_hash = Column(String, unique=True, nullable=False, index=True)  # Hash of the token for security
    user_id = Column(String, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False, index=True)  # When the token would naturally expire
    blacklisted_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Performance indexes
    __table_args__ = (
        Index('idx_blacklist_token_hash', 'token_hash'),  # Fast lookup by token hash
        Index('idx_blacklist_expires_at', 'expires_at'),  # For cleanup of expired entries
    )

    def __repr__(self):
        return f"<TokenBlacklist {self.token_hash[:8]}... for user {self.user_id}>"

