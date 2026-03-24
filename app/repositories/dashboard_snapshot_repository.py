"""Repository for dashboard snapshots."""
from typing import Optional
from sqlalchemy.orm import Session

from app.repositories.base import BaseRepository
from app.models.dashboard import DashboardSnapshot


class DashboardSnapshotRepository(BaseRepository[DashboardSnapshot]):
    def __init__(self):
        super().__init__(DashboardSnapshot)

    def get_latest_for_case(
        self,
        db: Session,
        case_id: str,
        user_id: str,
        case_version_id: str | None = None,
    ) -> Optional[DashboardSnapshot]:
        q = db.query(DashboardSnapshot).filter(
            DashboardSnapshot.case_id == case_id,
            DashboardSnapshot.user_id == user_id,
        )
        if case_version_id:
            q = q.filter(DashboardSnapshot.case_version_id == case_version_id)
        return q.order_by(DashboardSnapshot.version.desc()).first()

    def next_version(
        self,
        db: Session,
        case_id: str,
        user_id: str,
        case_version_id: str,
    ) -> int:
        latest = self.get_latest_for_case(db, case_id, user_id, case_version_id=case_version_id)
        return (latest.version + 1) if latest else 1

