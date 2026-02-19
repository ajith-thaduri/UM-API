"""Repository for CaseDateShift."""

from typing import Optional
import uuid
import random
from sqlalchemy.orm import Session

from app.models.case_date_shift import CaseDateShift
from app.repositories.base import BaseRepository


class CaseDateShiftRepository(BaseRepository[CaseDateShift]):
    """Repository for case date shift (Tier 2 de-identification)."""

    def __init__(self):
        super().__init__(CaseDateShift)

    def get_by_case_id(self, db: Session, case_id: str) -> Optional[CaseDateShift]:
        return db.query(CaseDateShift).filter(CaseDateShift.case_id == case_id).first()

    def get_or_create_shift_days(self, db: Session, case_id: str) -> int:
        """Return shift_days for case; create with random 0–30 if not present."""
        row = self.get_by_case_id(db, case_id)
        if row:
            return row.shift_days
        shift_days = random.randint(0, 30)
        record = CaseDateShift(
            id=str(uuid.uuid4()),
            case_id=case_id,
            shift_days=shift_days,
        )
        db.add(record)
        db.commit()
        return shift_days
