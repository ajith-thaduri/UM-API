"""Transaction model for wallet operations"""

from datetime import datetime
from sqlalchemy import Column, String, DateTime, Numeric, ForeignKey, Enum, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
import enum

from app.db.session import Base


class TransactionType(str, enum.Enum):
    """Transaction type enumeration"""
    CREDIT = "credit"
    DEBIT = "debit"


class TransactionStatus(str, enum.Enum):
    """Transaction status enumeration"""
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


class Transaction(Base):
    """Transaction model for wallet credits and debits"""

    __tablename__ = "transactions"

    id = Column(String, primary_key=True, index=True)
    wallet_id = Column(String, ForeignKey("wallets.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    type = Column(Enum(TransactionType, native_enum=False), nullable=False, index=True)
    amount = Column(Numeric(10, 2), nullable=False)
    description = Column(String, nullable=True)
    status = Column(Enum(TransactionStatus, native_enum=False), nullable=False, default=TransactionStatus.PENDING, index=True)
    payment_method = Column(String, nullable=True)  # e.g., 'stripe', 'trial', 'refund', 'usage'
    stripe_payment_intent_id = Column(String, nullable=True, index=True)  # For mock Stripe integration
    extra_metadata = Column(JSONB, nullable=True)  # Additional transaction data
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Relationships
    wallet = relationship("Wallet", back_populates="transactions")
    user = relationship("User", foreign_keys=[user_id])

    # Indexes
    __table_args__ = (
        Index('idx_transaction_user', 'user_id'),
        Index('idx_transaction_wallet', 'wallet_id'),
        Index('idx_transaction_created', 'created_at'),
        Index('idx_transaction_type_status', 'type', 'status'),
    )

    def __repr__(self):
        return f"<Transaction {self.id} - {self.type} - ${self.amount} - {self.status}>"

