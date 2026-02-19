"""Decision model for UM decisions"""

from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Enum, ForeignKey, Text
from sqlalchemy.orm import relationship
import enum

from app.db.session import Base


class DecisionType(str, enum.Enum):
    """Decision type enumeration"""

    APPROVED = "approved"
    DENIED = "denied"
    PENDING = "pending"
    NEEDS_CLARIFICATION = "needs_clarification"


class Decision(Base):
    """UM Decision model"""

    __tablename__ = "decisions"

    id = Column(String, primary_key=True, index=True)
    case_id = Column(String, ForeignKey("cases.id"), unique=True, nullable=False)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    decision_type = Column(
        Enum(DecisionType, native_enum=False, length=50),
        nullable=False
    )
    sub_status = Column(String, nullable=True)
    notes = Column(Text, nullable=True)
    decided_by = Column(String, nullable=False)  # User name or ID
    decided_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationship
    case = relationship("Case", back_populates="decision")

    def __repr__(self):
        return f"<Decision {self.decision_type} for Case {self.case_id}>"
