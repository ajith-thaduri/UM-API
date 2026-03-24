"""Repository for source links."""
from typing import List
from sqlalchemy.orm import Session

from app.repositories.base import BaseRepository
from app.models.dashboard import SourceLink


class SourceLinkRepository(BaseRepository[SourceLink]):
    def __init__(self):
        super().__init__(SourceLink)

    def list_for_facet(self, db: Session, facet_id: str) -> List[SourceLink]:
        return (
            db.query(SourceLink)
            .filter(SourceLink.facet_id == facet_id)
            .order_by(SourceLink.created_at.desc())
            .all()
        )

    def list_for_case(self, db: Session, case_id: str, user_id: str) -> List[SourceLink]:
        return (
            db.query(SourceLink)
            .filter(
                SourceLink.case_id == case_id,
                SourceLink.user_id == user_id
            )
            .order_by(SourceLink.created_at.desc())
            .all()
        )

    def list_for_case_version(
        self, db: Session, case_id: str, user_id: str, case_version_id: str
    ) -> List[SourceLink]:
        return (
            db.query(SourceLink)
            .filter(
                SourceLink.case_id == case_id,
                SourceLink.user_id == user_id,
                SourceLink.case_version_id == case_version_id,
            )
            .order_by(SourceLink.created_at.desc())
            .all()
        )

