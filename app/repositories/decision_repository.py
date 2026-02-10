"""Decision repository"""

from typing import Optional
from sqlalchemy.orm import Session

from app.repositories.base import BaseRepository
from app.models.decision import Decision, DecisionType


class DecisionRepository(BaseRepository[Decision]):
    """Repository for Decision model"""

    def __init__(self):
        super().__init__(Decision)

    def get_by_case_id(self, db: Session, case_id: str) -> Optional[Decision]:
        """
        Get decision by case ID

        Args:
            db: Database session
            case_id: Case ID

        Returns:
            Decision instance or None
        """
        return (
            db.query(Decision).filter(Decision.case_id == case_id).first()
        )

    def get_by_decision_type(
        self,
        db: Session,
        decision_type: DecisionType,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Decision]:
        """
        Get decisions by type

        Args:
            db: Database session
            decision_type: Decision type
            skip: Number of records to skip
            limit: Maximum number of records

        Returns:
            List of decisions
        """
        return (
            db.query(Decision)
            .filter(Decision.decision_type == decision_type)
            .order_by(Decision.decided_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

