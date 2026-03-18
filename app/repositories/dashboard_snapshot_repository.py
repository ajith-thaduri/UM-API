"""Repository for dashboard snapshots."""
from typing import Optional
from sqlalchemy.orm import Session

from app.repositories.base import BaseRepository
from app.models.dashboard import DashboardSnapshot


class DashboardSnapshotRepository(BaseRepository[DashboardSnapshot]):
    def __init__(self):
        super().__init__(DashboardSnapshot)

    def get_latest_for_case(self, db: Session, case_id: str, user_id: str) -> Optional[DashboardSnapshot]:
        return (
            db.query(DashboardSnapshot)
            .filter(
                DashboardSnapshot.case_id == case_id,
                DashboardSnapshot.user_id == user_id
            )
            .order_by(DashboardSnapshot.version.desc())
            .first()
        )

    def next_version(self, db: Session, case_id: str, user_id: str) -> int:
        latest = self.get_latest_for_case(db, case_id, user_id)
        return (latest.version + 1) if latest else 1

