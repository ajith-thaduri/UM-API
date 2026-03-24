"""Repository for CaseVersion and CaseVersionFile."""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.case_version import CaseVersion, CaseVersionFile, CaseVersionFileRole, CaseVersionStatus
from app.repositories.base import BaseRepository


class CaseVersionRepository(BaseRepository[CaseVersion]):
    def __init__(self):
        super().__init__(CaseVersion)

    def get_by_id_for_user(
        self, db: Session, version_id: str, user_id: str
    ) -> Optional[CaseVersion]:
        return (
            db.query(CaseVersion)
            .filter(CaseVersion.id == version_id, CaseVersion.user_id == user_id)
            .first()
        )

    def get_live_for_case(self, db: Session, case_id: str) -> Optional[CaseVersion]:
        return (
            db.query(CaseVersion)
            .filter(CaseVersion.case_id == case_id, CaseVersion.is_live.is_(True))
            .first()
        )

    def get_by_case_and_number(
        self, db: Session, case_id: str, version_number: int
    ) -> Optional[CaseVersion]:
        return (
            db.query(CaseVersion)
            .filter(CaseVersion.case_id == case_id, CaseVersion.version_number == version_number)
            .first()
        )

    def list_for_case(self, db: Session, case_id: str, user_id: str) -> List[CaseVersion]:
        return (
            db.query(CaseVersion)
            .filter(CaseVersion.case_id == case_id, CaseVersion.user_id == user_id)
            .order_by(CaseVersion.version_number.asc())
            .all()
        )

    def list_ready_for_case(self, db: Session, case_id: str, user_id: str) -> List[CaseVersion]:
        return (
            db.query(CaseVersion)
            .filter(
                CaseVersion.case_id == case_id,
                CaseVersion.user_id == user_id,
                CaseVersion.status == CaseVersionStatus.READY,
            )
            .order_by(CaseVersion.version_number.asc())
            .all()
        )

    def next_version_number(self, db: Session, case_id: str) -> int:
        row = (
            db.query(CaseVersion.version_number)
            .filter(CaseVersion.case_id == case_id)
            .order_by(CaseVersion.version_number.desc())
            .first()
        )
        return (row[0] + 1) if row else 1

    def unset_live_for_case(self, db: Session, case_id: str) -> None:
        db.query(CaseVersion).filter(CaseVersion.case_id == case_id, CaseVersion.is_live.is_(True)).update(
            {CaseVersion.is_live: False}
        )


class CaseVersionFileRepository(BaseRepository[CaseVersionFile]):
    def __init__(self):
        super().__init__(CaseVersionFile)

    def list_for_version(
        self, db: Session, case_version_id: str, ordered: bool = True
    ) -> List[CaseVersionFile]:
        q = db.query(CaseVersionFile).filter(CaseVersionFile.case_version_id == case_version_id)
        if ordered:
            q = q.order_by(CaseVersionFile.file_order_within_version)
        return q.all()

    def file_ids_for_version(self, db: Session, case_version_id: str) -> List[str]:
        rows = self.list_for_version(db, case_version_id, ordered=True)
        return [r.case_file_id for r in rows]

    def new_file_ids_for_version(self, db: Session, case_version_id: str) -> List[str]:
        return [
            r.case_file_id
            for r in self.list_for_version(db, case_version_id, ordered=True)
            if r.file_role == CaseVersionFileRole.NEW
        ]


case_version_repository = CaseVersionRepository()
case_version_file_repository = CaseVersionFileRepository()
