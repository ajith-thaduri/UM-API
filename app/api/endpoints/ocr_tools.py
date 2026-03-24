"""
OCR Lab API — diagnostic endpoints for testing OCR on uploaded PDFs.

Uses the same extraction pipeline as production (pdf_service + ocr stack).
- Read-only: no case or database state is modified.
- PDFs are never stored in S3 or DB. Upload is kept only in a request-scoped
  temp file for the duration of analysis, then deleted. Refreshing the page
  flushes any client-side state; the server holds no persisted copy.
"""

import logging
import os
import tempfile
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form

from app.api.endpoints.auth import get_current_user
from app.models.user import User
from app.services.ocr.lab_service import analyze_pdf_for_lab, get_engine_info

router = APIRouter()
logger = logging.getLogger(__name__)

MAX_UPLOAD_SIZE_MB = 50


@router.post("/analyze-pdf")
async def analyze_pdf(
    file: UploadFile = File(...),
    engine: str | None = Form(None),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Upload a PDF and run the same native/OCR extraction used by production.
    Returns document summary and per-page classification, text, and confidence.
    Optional form field 'engine': use this OCR engine for OCR pages (e.g. tesseract, ppstructure).
    """
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="A PDF file is required.")

    # Keep PDF only in memory then a temp file for this request; never S3 or DB
    content = await file.read()
    size_mb = len(content) / (1024 * 1024)
    if size_mb > MAX_UPLOAD_SIZE_MB:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size is {MAX_UPLOAD_SIZE_MB} MB.",
        )

    engine_hint = (engine or "").strip() or None
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(content)
            tmp_path = tmp.name
        result = analyze_pdf_for_lab(tmp_path, engine_hint=engine_hint)
        if result.get("error"):
            raise HTTPException(status_code=422, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("OCR lab analyze-pdf failed")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except Exception as e:
                logger.warning("Failed to delete temp file %s: %s", tmp_path, e)


@router.get("/engine-info")
async def engine_info(
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Return primary/fallback OCR engine availability for the lab UI."""
    return get_engine_info()


@router.post("/switch-engine")
async def switch_engine(
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Engine selection is controlled by env (OCR_PRIMARY_ENGINE, OCR_FALLBACK_ENGINE).
    This endpoint returns current engine info for UI consistency.
    """
    return {
        "message": "Engine is configured via OCR_PRIMARY_ENGINE / OCR_FALLBACK_ENGINE. Restart the API to change.",
        **get_engine_info(),
    }
