"""Extraction repository"""

from typing import Optional
from sqlalchemy.orm import Session

from app.repositories.base import BaseRepository
from app.models.extraction import ClinicalExtraction


class ExtractionRepository(BaseRepository[ClinicalExtraction]):
    """Repository for ClinicalExtraction model"""

    def __init__(self):
        super().__init__(ClinicalExtraction)

    def get_by_case_version_id(
        self, db: Session, case_version_id: str, user_id: Optional[str] = None
    ) -> Optional[ClinicalExtraction]:
        q = db.query(ClinicalExtraction).filter(
            ClinicalExtraction.case_version_id == case_version_id
        )
        if user_id:
            q = q.filter(ClinicalExtraction.user_id == user_id)
        return q.first()

    def get_by_case_id(
        self, db: Session, case_id: str, user_id: Optional[str] = None
    ) -> Optional[ClinicalExtraction]:
        """
        Return extraction for the case's live version (default UX).
        """
        from app.models.case import Case

        case = db.query(Case).filter(Case.id == case_id).first()
        if not case or not case.live_version_id:
            return None
        return self.get_by_case_version_id(db, case.live_version_id, user_id=user_id)

    def get_by_case_id_and_version(
        self,
        db: Session,
        case_id: str,
        case_version_id: Optional[str],
        user_id: Optional[str] = None,
    ) -> Optional[ClinicalExtraction]:
        """Resolve version: explicit case_version_id, else live."""
        from app.models.case import Case

        if case_version_id:
            q = db.query(ClinicalExtraction).filter(
                ClinicalExtraction.case_id == case_id,
                ClinicalExtraction.case_version_id == case_version_id,
            )
            if user_id:
                q = q.filter(ClinicalExtraction.user_id == user_id)
            return q.first()
        return self.get_by_case_id(db, case_id, user_id=user_id)

    def delete_by_case_id(self, db: Session, case_id: str) -> bool:
        """Delete all extractions for case (all versions)."""
        rows = db.query(ClinicalExtraction).filter(ClinicalExtraction.case_id == case_id).all()
        if not rows:
            return False
        for r in rows:
            db.delete(r)
        db.commit()
        return True

    def delete_by_case_version_id(self, db: Session, case_version_id: str) -> bool:
        extraction = self.get_by_case_version_id(db, case_version_id)
        if extraction:
            db.delete(extraction)
            db.commit()
            return True
        return False


# Singleton instance
extraction_repository = ExtractionRepository()
