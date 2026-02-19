"""Case file repository"""

from typing import List, Optional
from sqlalchemy.orm import Session

from app.repositories.base import BaseRepository
from app.models.case_file import CaseFile


class CaseFileRepository(BaseRepository[CaseFile]):
    """Repository for CaseFile model"""

    def __init__(self):
        super().__init__(CaseFile)

    def get_by_case_id(
        self, db: Session, case_id: str, ordered: bool = True
    ) -> List[CaseFile]:
        """
        Get all files for a case

        Args:
            db: Database session
            case_id: Case ID
            ordered: Whether to order by file_order

        Returns:
            List of case files
        """
        query = db.query(CaseFile).filter(CaseFile.case_id == case_id)
        if ordered:
            query = query.order_by(CaseFile.file_order)
        return query.all()

    def get_by_case_and_file_id(
        self, db: Session, case_id: str, file_id: str
    ) -> Optional[CaseFile]:
        """
        Get a specific file by case ID and file ID

        Args:
            db: Database session
            case_id: Case ID
            file_id: File ID

        Returns:
            CaseFile instance or None
        """
        return (
            db.query(CaseFile)
            .filter(CaseFile.case_id == case_id, CaseFile.id == file_id)
            .first()
        )

    def delete_by_case_id(self, db: Session, case_id: str) -> int:
        """
        Delete all files for a case

        Args:
            db: Database session
            case_id: Case ID

        Returns:
            Number of files deleted
        """
        count = db.query(CaseFile).filter(CaseFile.case_id == case_id).delete()
        db.commit()
        return count

