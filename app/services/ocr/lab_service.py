"""
OCR Lab orchestrator: read-only diagnostic wrapper around the production OCR pipeline.

Uses the same extraction path as ingestion (pdf_service.extract_text_with_coordinates)
so the lab validates the exact data shape used for View Source and chunking.
No database or case state is modified.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.services.pdf_service import pdf_service
from app.services.ocr.confidence import summary_eligible

logger = logging.getLogger(__name__)


def _ocr_service_available() -> bool:
    """Check if the OCR service is reachable (for lab engine info)."""
    url = (getattr(settings, "OCR_SERVICE_URL", None) or "").strip()
    if not url:
        return False
    try:
        import httpx
        with httpx.Client(timeout=10.0) as client:
            r = client.get(f"{url.rstrip('/')}/health")
            return r.status_code == 200
    except Exception:
        return False


def analyze_pdf_for_lab(pdf_path: str, engine_hint: Optional[str] = None) -> Dict[str, Any]:
    """
    Run the same mixed native/OCR extraction used by production and return
    a lab-friendly response with document summary and per-page details.

    Args:
        pdf_path: Local path to a PDF file (caller must write upload to temp and pass path).
        engine_hint: Optional engine id (e.g. tesseract, ppstructure) to use for OCR pages (lab testing).

    Returns:
        Lab response dict with document_summary and pages.
    """
    result = pdf_service.extract_text_with_coordinates(pdf_path, ocr_engine_hint=engine_hint)

    page_count = result.get("page_count", 0)
    ocr_pages = set(result.get("ocr_pages", []))
    document_confidence = result.get("document_confidence", 1.0)
    ocr_engine_used = result.get("ocr_engine_used")
    extraction_method = result.get("extraction_method", "direct")

    eligible, summary_message = summary_eligible(document_confidence)

    # Count classifications
    native_count = sum(1 for p in result.get("pages", []) if p.get("page_number") not in ocr_pages)
    ocr_count = len(ocr_pages)
    mixed_count = page_count - native_count - ocr_count
    if mixed_count < 0:
        mixed_count = 0

    ocr_service_available = _ocr_service_available()
    engine_info = {
        "primary_engine": "ocr_service",
        "primary_available": ocr_service_available,
        "fallback_engine": None,
        "fallback_available": False,
    }

    doc_badge = "Native text"
    if ocr_count == page_count and page_count > 0:
        doc_badge = "OCR-heavy"
    elif ocr_count > 0:
        doc_badge = "Mixed OCR"

    ocr_engine_available = engine_info["primary_available"]
    ocr_engine_message: Optional[str] = None
    if not ocr_engine_available and document_confidence == 0 and ocr_count == 0 and page_count > 0:
        ocr_engine_message = (
            "OCR service is not available. Set OCR_SERVICE_URL to the standalone OCR service base URL."
        )

    document_summary = {
        "page_count": page_count,
        "document_confidence": document_confidence,
        "summary_eligibility_eligible": eligible,
        "summary_eligibility_message": summary_message,
        "primary_engine": engine_info["primary_engine"],
        "fallback_engine": engine_info["fallback_engine"],
        "engine_used": ocr_engine_used,
        "native_page_count": native_count,
        "ocr_page_count": ocr_count,
        "mixed_page_count": mixed_count,
        "document_badge": doc_badge,
        "extraction_method": extraction_method,
        "ocr_engine_available": ocr_engine_available,
        "ocr_engine_message": ocr_engine_message,
    }

    pages: List[Dict[str, Any]] = []
    for p in result.get("pages", []):
        page_num = p.get("page_number", 0)
        text = p.get("text", "")
        segments = p.get("text_segments", [])
        in_ocr = page_num in ocr_pages
        classification = "ocr" if in_ocr else "native"
        ocr_trigger_reason = None
        if in_ocr:
            if len((text or "").strip()) < 50:
                ocr_trigger_reason = "low_text"
            elif not segments or len(segments) < 3:
                ocr_trigger_reason = "few_segments"
            else:
                ocr_trigger_reason = "placeholder_or_heuristic"

        pages.append({
            "page_number": page_num,
            "classification": classification,
            "native_text_length": len((text or "").strip()),
            "ocr_trigger_reason": ocr_trigger_reason,
            "text": text or "",
            "ocr_confidence": document_confidence if in_ocr else None,
            "engine_used": ocr_engine_used if in_ocr else None,
            "word_segment_count": len(segments),
            "text_segments": segments,
            "hybrid_stats": p.get("hybrid_stats") or {},
        })

    return {
        "document_summary": document_summary,
        "pages": pages,
        "error": result.get("error"),
    }


def _fetch_ocr_engines() -> List[Dict[str, Any]]:
    """Fetch list of engines from OCR service for lab dropdown."""
    url = (getattr(settings, "OCR_SERVICE_URL", None) or "").strip()
    if not url:
        return []
    try:
        import httpx
        with httpx.Client(timeout=10.0) as client:
            r = client.get(f"{url.rstrip('/')}/ocr/engines")
            if r.status_code != 200:
                return []
            data = r.json()
            return list(data.get("engines") or [])
    except Exception:
        return []


def get_engine_info() -> Dict[str, Any]:
    """Return OCR service availability and list of engines for the lab UI."""
    base = {
        "primary_engine": "ocr_service",
        "primary_available": _ocr_service_available(),
        "fallback_engine": None,
        "fallback_available": False,
    }
    engines = _fetch_ocr_engines()
    base["engines"] = engines
    return base


