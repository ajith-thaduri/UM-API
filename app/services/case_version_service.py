"""Create and manage CaseVersion snapshots for processing pipelines."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.case import Case
from app.models.case_file import CaseFile
from app.models.case_version import (
    CaseVersion,
    CaseVersionFile,
    CaseVersionFileRole,
    CaseVersionStatus,
)


def create_version_for_new_case(
    db: Session,
    case: Case,
    file_ids_ordered: List[str],
) -> CaseVersion:
    """First version after initial upload: all files are NEW."""
    v = CaseVersion(
        id=str(uuid.uuid4()),
        case_id=case.id,
        user_id=case.user_id,
        version_number=1,
        status=CaseVersionStatus.PROCESSING,
        is_live=True,
        base_version_id=None,
        processing_started_at=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc),
    )
    db.add(v)
    db.flush()
    for order, fid in enumerate(file_ids_ordered):
        db.add(
            CaseVersionFile(
                id=str(uuid.uuid4()),
                case_version_id=v.id,
                case_file_id=fid,
                file_role=CaseVersionFileRole.NEW,
                inherited_from_version_id=None,
                file_order_within_version=order,
            )
        )
        cf = db.query(CaseFile).filter(CaseFile.id == fid).first()
        if cf:
            cf.introduced_in_case_version_id = v.id
    case.live_version_id = v.id
    case.latest_version_number = 1
    case.processing_version_id = v.id
    db.add(case)
    db.commit()
    db.refresh(v)

    from app.services.case_vault_service import update_latest_used_for_version_files

    update_latest_used_for_version_files(db, v.id)
    db.commit()
    return v


def create_incremental_version(
    db: Session,
    case: Case,
    base_version: CaseVersion,
    new_case_file_ids: List[str],
    processing_metadata: Optional[Dict[str, Any]] = None,
) -> CaseVersion:
    """
    New version: snapshot = all files from base membership as EXISTING + new uploads as NEW.
    """
    next_n = (case.latest_version_number or 1) + 1
    v = CaseVersion(
        id=str(uuid.uuid4()),
        case_id=case.id,
        user_id=case.user_id,
        version_number=next_n,
        status=CaseVersionStatus.PROCESSING,
        is_live=False,
        base_version_id=base_version.id,
        processing_started_at=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc),
    )
    db.add(v)
    db.flush()

    # Copy membership from base as EXISTING
    from app.repositories.case_version_repository import case_version_file_repository

    base_files = case_version_file_repository.list_for_version(db, base_version.id, ordered=True)
    order = 0
    for bvf in base_files:
        db.add(
            CaseVersionFile(
                id=str(uuid.uuid4()),
                case_version_id=v.id,
                case_file_id=bvf.case_file_id,
                file_role=CaseVersionFileRole.EXISTING,
                inherited_from_version_id=base_version.id,
                file_order_within_version=order,
            )
        )
        order += 1

    for fid in new_case_file_ids:
        db.add(
            CaseVersionFile(
                id=str(uuid.uuid4()),
                case_version_id=v.id,
                case_file_id=fid,
                file_role=CaseVersionFileRole.NEW,
                inherited_from_version_id=None,
                file_order_within_version=order,
            )
        )
        cf = db.query(CaseFile).filter(CaseFile.id == fid).first()
        if cf:
            cf.introduced_in_case_version_id = v.id
        order += 1

    if processing_metadata is not None:
        v.version_processing_metadata = processing_metadata

    case.latest_version_number = next_n
    case.processing_version_id = v.id
    db.add(case)
    db.commit()
    db.refresh(v)

    from app.services.case_vault_service import update_latest_used_for_version_files

    update_latest_used_for_version_files(db, v.id)
    db.commit()
    return v


def promote_version_to_live(db: Session, case_id: str, version_id: str, user_id: str) -> Tuple[bool, str]:
    """Set is_live on the chosen READY version; demote others."""
    from app.repositories.case_version_repository import case_version_repository

    v = case_version_repository.get_by_id_for_user(db, version_id, user_id)
    if not v or v.case_id != case_id:
        return False, "Version not found"
    if v.status != CaseVersionStatus.READY:
        return False, "Only READY versions can be promoted"

    case = db.query(Case).filter(Case.id == case_id, Case.user_id == user_id).first()
    if not case:
        return False, "Case not found"

    case_version_repository.unset_live_for_case(db, case_id)
    v.is_live = True
    case.live_version_id = v.id
    db.commit()
    return True, "ok"
