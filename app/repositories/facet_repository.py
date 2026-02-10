"""Repository for facet results."""
from typing import List, Optional
from sqlalchemy.orm import Session

from app.repositories.base import BaseRepository
from app.models.dashboard import FacetResult, FacetType


class FacetRepository(BaseRepository[FacetResult]):
    def __init__(self):
        super().__init__(FacetResult)

    def get_by_snapshot_and_type(
        self, db: Session, snapshot_id: str, facet_type: FacetType
    ) -> Optional[FacetResult]:
        return (
            db.query(FacetResult)
            .filter(
                FacetResult.snapshot_id == snapshot_id,
                FacetResult.facet_type == facet_type,
            )
            .first()
        )

    def list_for_case(self, db: Session, case_id: str, user_id: str) -> List[FacetResult]:
        return (
            db.query(FacetResult)
            .filter(
                FacetResult.case_id == case_id,
                FacetResult.user_id == user_id
            )
            .order_by(FacetResult.created_at.desc())
            .all()
        )

    def list_for_snapshot(self, db: Session, snapshot_id: str) -> List[FacetResult]:
        return (
            db.query(FacetResult)
            .filter(FacetResult.snapshot_id == snapshot_id)
            .order_by(FacetResult.created_at.desc())
            .all()
        )

