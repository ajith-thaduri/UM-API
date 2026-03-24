"""Case document vault: all files for a case with per-version usage (Phase 2)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy.orm import Session

from app.models.case_file import CaseFile
from app.models.case_version import CaseVersion, CaseVersionFile
from app.repositories.case_version_repository import case_version_file_repository


def _base_file_id_set(db: Session, base_version_id: str) -> Set[str]:
    return set(case_version_file_repository.file_ids_for_version(db, base_version_id))


def build_case_vault_payload(
    db: Session,
    *,
    case_id: str,
    user_id: str,
    base_version_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    List all case files with version membership and optional base-version flags.
    """
    files = (
        db.query(CaseFile)
        .filter(CaseFile.case_id == case_id, CaseFile.user_id == user_id)
        .order_by(CaseFile.file_order)
        .all()
    )

    base_ids: Set[str] = set()
    if base_version_id:
        bv = (
            db.query(CaseVersion)
            .filter(
                CaseVersion.id == base_version_id,
                CaseVersion.case_id == case_id,
                CaseVersion.user_id == user_id,
            )
            .first()
        )
        if bv:
            base_ids = _base_file_id_set(db, base_version_id)

    # Map case_file_id -> list of {version_id, version_number}
    memberships: Dict[str, List[Dict[str, Any]]] = {}
    rows = (
        db.query(CaseVersionFile, CaseVersion.version_number, CaseVersion.id)
        .join(CaseVersion, CaseVersion.id == CaseVersionFile.case_version_id)
        .filter(CaseVersion.case_id == case_id, CaseVersion.user_id == user_id)
        .all()
    )
    for cvf, vnum, version_row_id in rows:
        memberships.setdefault(cvf.case_file_id, []).append(
            {"version_id": version_row_id, "version_number": vnum}
        )

    out_files: List[Dict[str, Any]] = []
    for cf in files:
        used_in = sorted(
            memberships.get(cf.id, []),
            key=lambda x: x["version_number"],
        )
        in_base = cf.id in base_ids if base_ids else False
        out_files.append(
            {
                "id": cf.id,
                "file_name": cf.file_name,
                "file_order": cf.file_order,
                "page_count": cf.page_count,
                "uploaded_at": cf.uploaded_at.isoformat() if cf.uploaded_at else None,
                "document_type": cf.document_type,
                "introduced_in_case_version_id": cf.introduced_in_case_version_id,
                "latest_used_in_case_version_id": getattr(
                    cf, "latest_used_in_case_version_id", None
                ),
                "used_in_versions": used_in,
                "already_in_selected_base": in_base if base_version_id else None,
                "available_to_attach_without_reupload": bool(base_version_id)
                and not in_base
                if base_version_id
                else None,
            }
        )

    return {"case_id": case_id, "base_version_id": base_version_id, "files": out_files}


def validate_vault_selection_for_new_version(
    db: Session,
    *,
    case_id: str,
    user_id: str,
    base_version: CaseVersion,
    selected_existing_file_ids: List[str],
) -> Tuple[bool, str]:
    """Ensure selected vault files belong to case and are not already in base snapshot."""
    base_member = _base_file_id_set(db, base_version.id)
    for fid in selected_existing_file_ids:
        cf = (
            db.query(CaseFile)
            .filter(
                CaseFile.id == fid,
                CaseFile.case_id == case_id,
                CaseFile.user_id == user_id,
            )
            .first()
        )
        if not cf:
            return False, f"Case file {fid} not found for this case"
        if fid in base_member:
            return False, f"File {cf.file_name} is already in the selected base version"
    return True, "ok"


def update_latest_used_for_version_files(db: Session, case_version_id: str) -> None:
    """After creating a version snapshot, stamp latest_used on member files."""
    rows = case_version_file_repository.list_for_version(db, case_version_id, ordered=False)
    for vr in rows:
        cf = db.query(CaseFile).filter(CaseFile.id == vr.case_file_id).first()
        if cf and hasattr(cf, "latest_used_in_case_version_id"):
            cf.latest_used_in_case_version_id = case_version_id
            db.add(cf)
