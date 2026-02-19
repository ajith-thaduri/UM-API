"""Extraction repository"""

from typing import Optional
from sqlalchemy.orm import Session

from app.repositories.base import BaseRepository
from app.models.extraction import ClinicalExtraction


class ExtractionRepository(BaseRepository[ClinicalExtraction]):
    """Repository for ClinicalExtraction model"""

    def __init__(self):
        super().__init__(ClinicalExtraction)

    def get_by_case_id(
        self, db: Session, case_id: str, user_id: Optional[str] = None
    ) -> Optional[ClinicalExtraction]:
        """
        Get extraction by case ID, optionally filtered by user_id

        Args:
            db: Database session
            case_id: Case ID
            user_id: Optional user ID to filter by

        Returns:
            ClinicalExtraction instance or None
        """
        query = db.query(ClinicalExtraction).filter(ClinicalExtraction.case_id == case_id)
        if user_id:
            query = query.filter(ClinicalExtraction.user_id == user_id)
        return query.first()

    def delete_by_case_id(self, db: Session, case_id: str) -> bool:
        """
        Delete extraction by case ID

        Args:
            db: Database session
            case_id: Case ID

        Returns:
            True if deleted, False if not found
        """
        extraction = self.get_by_case_id(db, case_id)
        if extraction:
            db.delete(extraction)
            db.commit()
            return True
        return False


# Singleton instance
extraction_repository = ExtractionRepository()
