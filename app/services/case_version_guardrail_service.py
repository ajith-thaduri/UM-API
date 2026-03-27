"""Advisory guardrails for incremental case version uploads (branch flow)."""

from __future__ import annotations

import logging
import re
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy.orm import Session

from app.models.case import Case
from app.models.case_file import CaseFile
from app.repositories.extraction_repository import extraction_repository
from app.services.llm.llm_factory import get_tier1_llm_service
from app.services.llm_utils import extract_json_from_response
from app.services.pdf_analyzer_service import pdf_analyzer_service
from app.services.pdf_service import pdf_service

logger = logging.getLogger(__name__)

DUPLICATE_TEXT_RATIO_THRESHOLD = 0.85
PATIENT_NAME_RATIO_MIN = 0.55
_MAX_EXISTING_FILES_TO_SCAN = 50


def _normalize_ws(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def leading_pdf_text(file_path: str, max_pages: int = 3, max_chars: int = 8000) -> str:
    try:
        ex = pdf_service.extract_text_from_pdf(file_path)
        parts: List[str] = []
        for p in (ex.get("pages") or [])[:max_pages]:
            parts.append(p.get("text") or "")
        return _normalize_ws("\n".join(parts))[:max_chars].lower()
    except Exception as e:
        logger.warning("leading_pdf_text failed for %s: %s", file_path, e)
        return ""


def _name_similarity(case_name: str, extracted_name: Optional[str]) -> float:
    if not extracted_name or not case_name:
        return 1.0
    a = _normalize_ws(case_name).lower()
    b = _normalize_ws(extracted_name).lower()
    if not b or len(b) < 3:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


def _collect_existing_leading_texts(
    db: Session,
    *,
    case_id: str,
    user_id: str,
    exclude_file_ids: Optional[Set[str]] = None,
) -> List[Tuple[str, str, str]]:
    """Return (file_id, file_name, leading_text_lower) for case PDFs."""
    rows = (
        db.query(CaseFile)
        .filter(CaseFile.case_id == case_id, CaseFile.user_id == user_id)
        .order_by(CaseFile.file_order)
        .limit(_MAX_EXISTING_FILES_TO_SCAN)
        .all()
    )
    out: List[Tuple[str, str, str]] = []
    for cf in rows:
        if exclude_file_ids and cf.id in exclude_file_ids:
            continue
        lt = leading_pdf_text(cf.file_path)
        if lt and len(lt) >= 40:
            out.append((cf.id, cf.file_name or cf.id, lt))
    return out


def _best_text_duplicate(
    new_text: str, existing: List[Tuple[str, str, str]]
) -> Optional[Dict[str, Any]]:
    if not new_text or len(new_text) < 80:
        return None
    best: Optional[Dict[str, Any]] = None
    best_ratio = 0.0
    for fid, fname, ex_text in existing:
        if not ex_text:
            continue
        r = SequenceMatcher(None, new_text, ex_text).ratio()
        if r > best_ratio:
            best_ratio = r
            best = {"file_id": fid, "file_name": fname, "similarity": round(r, 3)}
    return best


async def _llm_patient_alignment(
    case_patient_name: str, case_summary: str, doc_preview: str
) -> Tuple[Optional[bool], str]:
    llm = get_tier1_llm_service()
    if not llm.is_available():
        return None, ""
    prompt = f"""Case patient name on file: {case_patient_name}
Brief case context:
{case_summary[:2000]}

New document excerpt:
{doc_preview[:3500]}

Reply with JSON only: {{"aligned_to_case_patient": true or false, "reason": "one short sentence"}}"""
    try:
        response, _ = await llm.chat_completion(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=220,
        )
        data = extract_json_from_response(response)
        aligned = data.get("aligned_to_case_patient")
        if isinstance(aligned, bool):
            return aligned, str(data.get("reason") or "")
    except Exception as e:
        logger.debug("LLM alignment skipped: %s", e)
    return None, ""


async def evaluate_branch_new_uploads(
    db: Session,
    *,
    case: Case,
    base_version_id: str,
    user_id: str,
    uploads: List[Tuple[str, str]],
    exclude_existing_file_ids: Optional[Set[str]] = None,
) -> Dict[str, Any]:
    """
    uploads: list of (storage_path_or_temp_path, original_filename).
    exclude_existing_file_ids: when new rows already exist in DB, exclude them from duplicate corpus.
    """
    extraction = extraction_repository.get_by_case_id_and_version(
        db, case.id, base_version_id, user_id=user_id
    )
    case_summary_snip = ""
    if extraction:
        chunks = [
            str(extraction.summary or "")[:1200],
            str(extraction.executive_summary or "")[:800],
        ]
        case_summary_snip = _normalize_ws("\n".join(c for c in chunks if c))

    existing = _collect_existing_leading_texts(
        db,
        case_id=case.id,
        user_id=user_id,
        exclude_file_ids=exclude_existing_file_ids,
    )

    out_files: List[Dict[str, Any]] = []
    batch_texts: List[Tuple[str, str]] = []

    for file_path, orig_name in uploads:
        issues: List[Dict[str, Any]] = []
        text = leading_pdf_text(file_path)

        detected_type = "unknown"
        doc_patient_name: Optional[str] = None

        try:
            analysis = await pdf_analyzer_service.analyze_for_upload([file_path])
        except Exception as e:
            logger.error("analyze_for_upload failed: %s", e, exc_info=True)
            analysis = None

        if analysis and analysis.files:
            fa = analysis.files[0]
            detected_type = fa.detected_type
            if detected_type.startswith("non_medical_"):
                cat = detected_type.replace("non_medical_", "").replace("_", " ")
                issues.append(
                    {
                        "code": "non_medical",
                        "severity": "warning",
                        "message": f"Document may be non-clinical ({cat})",
                        "details": {"detected_type": detected_type},
                    }
                )

        if analysis and analysis.patient_info:
            doc_patient_name = analysis.patient_info.name

        if case.patient_name and doc_patient_name:
            ratio = _name_similarity(case.patient_name, doc_patient_name)
            if ratio < PATIENT_NAME_RATIO_MIN:
                issues.append(
                    {
                        "code": "not_patient_related",
                        "severity": "warning",
                        "message": (
                            "Extracted patient name may not match this case "
                            f"({doc_patient_name} vs case record)"
                        ),
                        "details": {
                            "case_patient_name": case.patient_name,
                            "document_patient_name": doc_patient_name,
                            "name_similarity": round(ratio, 3),
                        },
                    }
                )
        elif case.patient_name and not doc_patient_name and text and len(text) > 120:
            related, reason = await _llm_patient_alignment(
                case.patient_name, case_summary_snip, text[:4000]
            )
            if related is False:
                issues.append(
                    {
                        "code": "not_patient_related",
                        "severity": "warning",
                        "message": reason or "Document may not belong to this patient/case",
                        "details": {},
                    }
                )

        best_dup = _best_text_duplicate(text, existing)
        if best_dup and best_dup["similarity"] >= DUPLICATE_TEXT_RATIO_THRESHOLD:
            issues.append(
                {
                    "code": "possible_duplicate",
                    "severity": "warning",
                    "message": f"High similarity to existing document: {best_dup['file_name']}",
                    "details": {
                        "matched_file_id": best_dup["file_id"],
                        "matched_file_name": best_dup["file_name"],
                        "similarity": best_dup["similarity"],
                    },
                }
            )

        for other_name, other_text in batch_texts:
            sim = SequenceMatcher(None, text, other_text).ratio()
            if sim >= DUPLICATE_TEXT_RATIO_THRESHOLD:
                issues.append(
                    {
                        "code": "possible_duplicate",
                        "severity": "warning",
                        "message": f"High similarity to another new upload in this batch: {other_name}",
                        "details": {
                            "matched_file_name": other_name,
                            "similarity": round(sim, 3),
                        },
                    }
                )

        batch_texts.append((orig_name, text))

        out_files.append(
            {
                "file_name": orig_name,
                "detected_document_type": detected_type,
                "issues": issues,
            }
        )

    has_warnings = any(f["issues"] for f in out_files)
    warning_count = sum(len(f["issues"]) for f in out_files)
    return {
        "has_warnings": has_warnings,
        "warning_count": warning_count,
        "files": out_files,
    }


def try_delete_uploaded_blob(file_path_key: str) -> None:
    """Best-effort delete for a CaseFile.file_path value (local key or S3 key)."""
    from app.core.config import settings

    if not file_path_key:
        return
    try:
        if settings.STORAGE_TYPE == "local":
            from pathlib import Path

            from app.services.local_storage_service import local_storage_service

            p = Path(local_storage_service.storage_path) / file_path_key
            if p.is_file():
                p.unlink()
        elif settings.STORAGE_TYPE == "s3":
            from botocore.exceptions import ClientError

            from app.services.s3_storage_service import s3_storage_service

            client = s3_storage_service._get_client()
            client.delete_object(Bucket=s3_storage_service.bucket_name, Key=file_path_key)
    except Exception as e:
        logger.warning("Could not delete storage blob %s: %s", file_path_key, e)
