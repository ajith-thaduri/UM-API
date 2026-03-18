"""Note repository"""

from typing import List
from sqlalchemy.orm import Session

from app.repositories.base import BaseRepository
from app.models.note import CaseNote


class NoteRepository(BaseRepository[CaseNote]):
    """Repository for CaseNote model"""

    def __init__(self):
        super().__init__(CaseNote)

    def get_by_case_id(
        self, db: Session, case_id: str, ordered: bool = True
    ) -> List[CaseNote]:
        """
        Get all notes for a case

        Args:
            db: Database session
            case_id: Case ID
            ordered: Whether to order by created_at desc

        Returns:
            List of case notes
        """
        query = db.query(CaseNote).filter(CaseNote.case_id == case_id)
        if ordered:
            query = query.order_by(CaseNote.created_at.desc())
        return query.all()

    def delete_by_case_id(self, db: Session, case_id: str) -> int:
        """
        Delete all notes for a case

        Args:
            db: Database session
            case_id: Case ID

        Returns:
            Number of notes deleted
        """
        count = db.query(CaseNote).filter(CaseNote.case_id == case_id).delete()
        db.commit()
        return count

