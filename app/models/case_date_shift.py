"""Case date shift model for HIPAA-compliant Tier 2 (Claude) summary generation.

Stores a unique per-case day offset (0–30) used to shift all dates before sending
data to Tier 2. After receiving the summary, dates are reverse-shifted so no PHI
dates are ever sent to external models.
"""

from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, UniqueConstraint

from app.db.session import Base


class CaseDateShift(Base):
    """Per-case date shift for Tier 2 de-identification."""

    __tablename__ = "case_date_shifts"

    id = Column(String, primary_key=True, index=True)
    case_id = Column(String, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True, unique=True)
    shift_days = Column(Integer, nullable=False)  # 0–30; applied as (date + shift_days) when sending to Tier 2
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (UniqueConstraint("case_id", name="uq_case_date_shift_case_id"),)

    def __repr__(self):
        return f"<CaseDateShift case_id={self.case_id} shift_days={self.shift_days}>"
