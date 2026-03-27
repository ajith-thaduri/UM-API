"""Case processing version APIs: list, append documents, promote live."""

import json
import logging
import os
import shutil
import tempfile
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.api.endpoints.auth import get_current_user
from app.core.redis import enqueue_case_processing
from app.db.session import get_db
from app.db.dependencies import get_case_repository, get_case_file_repository
from app.models.case import Case, CaseStatus
from app.models.case_file import CaseFile
from app.models.case_version import CaseVersion, CaseVersionStatus
from app.models.user import User
from app.repositories.case_file_repository import CaseFileRepository
from app.repositories.case_repository import CaseRepository
from app.repositories.case_version_repository import (
    case_version_file_repository,
    case_version_repository,
)
from app.services.case_version_service import create_incremental_version, promote_version_to_live
from app.services.case_vault_service import (
    build_case_vault_payload,
    validate_vault_selection_for_new_version,
)
from app.services.case_version_guardrail_service import (
    evaluate_branch_new_uploads,
    try_delete_uploaded_blob,
)
from app.services.pdf_service import pdf_service
from app.services.storage_service import storage_service

logger = logging.getLogger(__name__)

router = APIRouter(redirect_slashes=False)


def _version_to_dict(v: CaseVersion, db: Optional[Session] = None) -> Dict[str, Any]:
    base_version_number: Optional[int] = None
    if v.base_version_id and db is not None:
        bv = db.query(CaseVersion).filter(CaseVersion.id == v.base_version_id).first()
        if bv:
            base_version_number = bv.version_number
    meta = getattr(v, "version_processing_metadata", None)
    if meta and isinstance(meta, dict) and meta.get("base_version_number") is not None:
        base_version_number = meta.get("base_version_number") or base_version_number
    return {
        "id": v.id,
        "case_id": v.case_id,
        "version_number": v.version_number,
        "status": v.status.value if hasattr(v.status, "value") else str(v.status),
        "is_live": v.is_live,
        "base_version_id": v.base_version_id,
        "base_version_number": base_version_number,
        "change_summary": v.change_summary,
        "change_reasoning": v.change_reasoning,
        "revision_impact_report": getattr(v, "revision_impact_report", None),
        "confidence_summary": getattr(v, "confidence_summary", None),
        "review_flags": getattr(v, "review_flags", None),
        "materiality_label": getattr(v, "materiality_label", None),
        "version_processing_metadata": getattr(v, "version_processing_metadata", None),
        "processed_at": v.processed_at.isoformat() if v.processed_at else None,
        "created_at": v.created_at.isoformat() if v.created_at else None,
        "record_count": v.record_count,
        "page_count": v.page_count,
    }


@router.get("/{case_id}/versions")
async def list_case_versions(
    case_id: str,
    db: Session = Depends(get_db),
    case_repo: CaseRepository = Depends(get_case_repository),
    current_user: User = Depends(get_current_user),
):
    case = case_repo.get_by_id(db, case_id, user_id=current_user.id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    rows = case_version_repository.list_for_case(db, case_id, current_user.id)
    return {
        "case_id": case_id,
        "versions": [_version_to_dict(v, db) for v in rows],
    }


@router.get("/{case_id}/versions/ready")
async def list_ready_case_versions(
    case_id: str,
    db: Session = Depends(get_db),
    case_repo: CaseRepository = Depends(get_case_repository),
    current_user: User = Depends(get_current_user),
):
    """READY versions only (for base-version picker in create-version UI)."""
    case = case_repo.get_by_id(db, case_id, user_id=current_user.id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    rows = case_version_repository.list_ready_for_case(db, case_id, current_user.id)
    return {
        "case_id": case_id,
        "versions": [_version_to_dict(v, db) for v in rows],
    }


@router.get("/{case_id}/versions/{version_id}")
async def get_case_version(
    case_id: str,
    version_id: str,
    db: Session = Depends(get_db),
    case_repo: CaseRepository = Depends(get_case_repository),
    current_user: User = Depends(get_current_user),
):
    case = case_repo.get_by_id(db, case_id, user_id=current_user.id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    v = case_version_repository.get_by_id_for_user(db, version_id, current_user.id)
    if not v or v.case_id != case_id:
        raise HTTPException(status_code=404, detail="Version not found")
    from app.repositories.case_version_repository import case_version_file_repository

    vfiles = case_version_file_repository.list_for_version(db, v.id, ordered=True)
    existing_docs: List[Dict[str, Any]] = []
    new_docs: List[Dict[str, Any]] = []
    for vf in vfiles:
        cf = db.query(CaseFile).filter(CaseFile.id == vf.case_file_id).first()
        if not cf:
            continue
        entry = {
            "file_id": cf.id,
            "file_name": cf.file_name,
            "file_order": vf.file_order_within_version,
        }
        role = vf.file_role.value if hasattr(vf.file_role, "value") else str(vf.file_role)
        if role == "existing":
            existing_docs.append(entry)
        else:
            new_docs.append(entry)
    out = _version_to_dict(v, db)
    out["existing_documents"] = existing_docs
    out["new_documents"] = new_docs
    return out


@router.get("/{case_id}/vault")
async def get_case_vault(
    case_id: str,
    base_version_id: Optional[str] = None,
    db: Session = Depends(get_db),
    case_repo: CaseRepository = Depends(get_case_repository),
    current_user: User = Depends(get_current_user),
):
    """All PDFs for the case with version usage; optional base highlights attachable vault docs."""
    case = case_repo.get_by_id(db, case_id, user_id=current_user.id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    if base_version_id:
        bv = case_version_repository.get_by_id_for_user(db, base_version_id, current_user.id)
        if not bv or bv.case_id != case_id:
            raise HTTPException(status_code=404, detail="Base version not found")
    return build_case_vault_payload(
        db, case_id=case_id, user_id=current_user.id, base_version_id=base_version_id
    )


@router.post("/{case_id}/versions/guardrails")
async def branch_version_upload_guardrails(
    case_id: str,
    base_version_id: Optional[str] = Form(None),
    files: Optional[List[UploadFile]] = File(None),
    db: Session = Depends(get_db),
    case_repo: CaseRepository = Depends(get_case_repository),
    current_user: User = Depends(get_current_user),
):
    """
    Advisory checks on new PDFs before creating a version (no DB writes).
    Saves uploads to a temp directory, runs Tier-1 analysis + duplicate heuristics, then deletes temp files.
    """
    case = case_repo.get_by_id(db, case_id, user_id=current_user.id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    if base_version_id:
        base = case_version_repository.get_by_id_for_user(db, base_version_id, current_user.id)
        if not base or base.case_id != case_id:
            raise HTTPException(status_code=404, detail="Base version not found")
        st = base.status.value if hasattr(base.status, "value") else str(base.status)
        if st != CaseVersionStatus.READY.value:
            raise HTTPException(status_code=400, detail="Base version must be READY")
    else:
        base = case_version_repository.get_live_for_case(db, case_id)
        if not base:
            raise HTTPException(
                status_code=400,
                detail="Case has no live version; specify base_version_id",
            )

    upload_list = files if files else []
    for f in upload_list:
        if not f.filename or not f.filename.lower().endswith(".pdf"):
            raise HTTPException(status_code=400, detail="Only PDF files are supported")

    if not upload_list:
        raise HTTPException(status_code=400, detail="Provide at least one PDF to validate")

    tmpdir = tempfile.mkdtemp(prefix="um_branch_guard_")
    paths: List[tuple] = []
    try:
        for uf in upload_list:
            safe_name = os.path.basename(uf.filename or "upload.pdf")
            dest = os.path.join(tmpdir, f"{uuid.uuid4().hex}_{safe_name}")
            content = await uf.read()
            with open(dest, "wb") as out:
                out.write(content)
            paths.append((dest, uf.filename or safe_name))

        result = await evaluate_branch_new_uploads(
            db,
            case=case,
            base_version_id=base.id,
            user_id=current_user.id,
            uploads=paths,
            exclude_existing_file_ids=None,
        )
        result["case_id"] = case_id
        result["base_version_id"] = base.id
        return result
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


@router.post("/{case_id}/versions/{version_id}/promote")
async def promote_version(
    case_id: str,
    version_id: str,
    db: Session = Depends(get_db),
    case_repo: CaseRepository = Depends(get_case_repository),
    current_user: User = Depends(get_current_user),
):
    ok, msg = promote_version_to_live(db, case_id, version_id, current_user.id)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"message": "Version promoted to live", "case_id": case_id, "live_version_id": version_id}


@router.post("/{case_id}/versions")
async def create_case_version_with_files(
    case_id: str,
    base_version_id: Optional[str] = Form(None),
    selected_existing_file_ids: Optional[str] = Form(None),
    guardrails_acknowledged: Optional[str] = Form(None),
    files: Optional[List[UploadFile]] = File(None),
    db: Session = Depends(get_db),
    case_repo: CaseRepository = Depends(get_case_repository),
    case_file_repo: CaseFileRepository = Depends(get_case_file_repository),
    current_user: User = Depends(get_current_user),
):
    """
    Create the next immutable version from a READY base (default: live) plus:
    - existing case vault PDFs not already in the base snapshot, and/or
    - newly uploaded PDFs.
    """
    case = case_repo.get_by_id(db, case_id, user_id=current_user.id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    if base_version_id:
        base = case_version_repository.get_by_id_for_user(db, base_version_id, current_user.id)
        if not base or base.case_id != case_id:
            raise HTTPException(status_code=404, detail="Base version not found")
        st = base.status.value if hasattr(base.status, "value") else str(base.status)
        if st != CaseVersionStatus.READY.value:
            raise HTTPException(status_code=400, detail="Base version must be READY")
    else:
        base = case_version_repository.get_live_for_case(db, case_id)
        if not base:
            raise HTTPException(
                status_code=400,
                detail="Case has no live version; specify base_version_id",
            )

    selected_ids: List[str] = []
    if selected_existing_file_ids:
        try:
            parsed = json.loads(selected_existing_file_ids)
            if not isinstance(parsed, list):
                raise ValueError("not a list")
            selected_ids = [str(x) for x in parsed]
        except (json.JSONDecodeError, ValueError):
            raise HTTPException(
                status_code=400,
                detail="selected_existing_file_ids must be a JSON array of case file UUID strings",
            )

    ok, msg = validate_vault_selection_for_new_version(
        db,
        case_id=case_id,
        user_id=current_user.id,
        base_version=base,
        selected_existing_file_ids=selected_ids,
    )
    if not ok:
        raise HTTPException(status_code=400, detail=msg)

    upload_list = files if files else []
    for f in upload_list:
        if not f.filename or not f.filename.lower().endswith(".pdf"):
            raise HTTPException(status_code=400, detail="Only PDF files are supported")

    new_upload_ids: List[str] = []
    new_case_files: List[CaseFile] = []
    total_pages_add = 0
    if upload_list:
        file_results = await storage_service.save_case_files(
            case_id, upload_list, user_id=current_user.id
        )
        max_order = db.query(CaseFile).filter(CaseFile.case_id == case_id).count()
        for idx, (file_path, file_size, original_filename) in enumerate(file_results):
            page_count = pdf_service.count_pages(file_path)
            total_pages_add += page_count
            cf = CaseFile(
                id=str(uuid.uuid4()),
                case_id=case_id,
                user_id=current_user.id,
                file_name=original_filename,
                file_path=file_path,
                file_size=file_size,
                page_count=page_count,
                file_order=max_order + idx,
                uploaded_at=datetime.utcnow(),
            )
            case_file_repo.create(db, cf)
            new_upload_ids.append(cf.id)
            new_case_files.append(cf)

    if new_case_files:
        ack = (guardrails_acknowledged or "").strip().lower() in ("true", "1", "yes")
        gr = await evaluate_branch_new_uploads(
            db,
            case=case,
            base_version_id=base.id,
            user_id=current_user.id,
            uploads=[(cf.file_path, cf.file_name) for cf in new_case_files],
            exclude_existing_file_ids=set(new_upload_ids),
        )
        if gr.get("has_warnings") and not ack:
            for cf in new_case_files:
                try_delete_uploaded_blob(cf.file_path)
                case_file_repo.delete(db, cf.id)
            raise HTTPException(
                status_code=400,
                detail={
                    "message": "Upload guardrails reported warnings. Review findings or pass guardrails_acknowledged=true to proceed.",
                    "guardrails": gr,
                },
            )

    new_snapshot_ids = list(dict.fromkeys(selected_ids + new_upload_ids))
    if not new_snapshot_ids:
        raise HTTPException(
            status_code=400,
            detail="Add at least one document: select unused vault PDFs and/or upload new PDFs",
        )

    carried = len(case_version_file_repository.list_for_version(db, base.id, ordered=True))
    processing_metadata: Dict[str, Any] = {
        "base_version_id": base.id,
        "base_version_number": base.version_number,
        "added_existing_vault_file_ids": selected_ids,
        "added_new_upload_file_ids": new_upload_ids,
        "carried_forward_file_count": carried,
    }

    if total_pages_add:
        case.page_count = (case.page_count or 0) + total_pages_add
    if new_upload_ids:
        case.record_count = (case.record_count or 0) + len(new_upload_ids)
    case.status = CaseStatus.UPLOADED
    case_repo.update(db, case)

    cv = create_incremental_version(
        db, case, base, new_snapshot_ids, processing_metadata=processing_metadata
    )

    job_id = await enqueue_case_processing(case_id, str(current_user.id), cv.id)
    if job_id is None:
        logger.error(
            "Redis enqueue failed for new case version %s; user must retry or fix queue",
            cv.id,
        )

    return {
        "case_id": case_id,
        "case_version_id": cv.id,
        "version_number": cv.version_number,
        "base_version_id": base.id,
        "base_version_number": base.version_number,
        "added_existing_vault_file_ids": selected_ids,
        "added_new_upload_file_ids": new_upload_ids,
        "document_selection_summary": {
            "carried_forward_from_base": carried,
            "attached_from_vault": len(selected_ids),
            "new_uploads": len(new_upload_ids),
        },
        "message": "New version created; processing started"
        if job_id
        else "New version created but job queue unavailable — retry shortly or check Redis/workers",
        "job_id": job_id,
        "enqueue_failed": job_id is None,
    }


@router.get("/{case_id}/versions/{version_id}/diff")
async def get_version_diff(
    case_id: str,
    version_id: str,
    db: Session = Depends(get_db),
    case_repo: CaseRepository = Depends(get_case_repository),
    current_user: User = Depends(get_current_user),
):
    v = case_version_repository.get_by_id_for_user(db, version_id, current_user.id)
    if not v or v.case_id != case_id:
        raise HTTPException(status_code=404, detail="Version not found")
    return {
        "case_id": case_id,
        "version_id": version_id,
        "change_reasoning": v.change_reasoning or {},
        "change_summary": v.change_summary,
        "revision_impact_report": getattr(v, "revision_impact_report", None) or {},
        "confidence_summary": getattr(v, "confidence_summary", None) or {},
        "review_flags": getattr(v, "review_flags", None) or [],
        "materiality_label": getattr(v, "materiality_label", None),
    }
