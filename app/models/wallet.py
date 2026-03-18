"""Wallet model for user balance management"""

from datetime import datetime
from sqlalchemy import Column, String, DateTime, Numeric, ForeignKey, Index
from sqlalchemy.orm import relationship

from app.db.session import Base


class Wallet(Base):
    """Wallet model for managing user balance"""

    __tablename__ = "wallets"

    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    balance = Column(Numeric(10, 2), nullable=False, default=50.00)  # Default $50 trial balance
    currency = Column(String, nullable=False, default="USD")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Performance indexes
    __table_args__ = (
        Index('idx_wallet_user', 'user_id'),
    )

    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    transactions = relationship("Transaction", back_populates="wallet", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Wallet {self.id} - User {self.user_id} - Balance: ${self.balance}>"

