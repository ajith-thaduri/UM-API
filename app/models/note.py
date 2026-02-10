"""Case note model"""

from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship

from app.db.session import Base


class CaseNote(Base):
    """Case note model for comments and annotations"""

    __tablename__ = "case_notes"

    id = Column(String, primary_key=True, index=True)
    case_id = Column(String, ForeignKey("cases.id"), nullable=False, index=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    author = Column(String, nullable=False)
    text = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationship
    case = relationship("Case", back_populates="notes")

    def __repr__(self):
        return f"<CaseNote by {self.author} on {self.created_at}>"
