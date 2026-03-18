"""OCR confidence aggregation and summary gating rules."""

from __future__ import annotations

import logging
from typing import List

from app.core.config import settings
from app.services.ocr.types import OCRPageResult, PageExtractionMode

logger = logging.getLogger(__name__)


def aggregate_document_confidence(pages: List[OCRPageResult]) -> float:
    """
    Compute a single document-level confidence from page-level confidences.
    Uses minimum of page confidences so one bad page pulls down the score.
    """
    if not pages:
        return 0.0
    confidences = [p.page_confidence for p in pages]
    return min(confidences)


def summary_eligible(
    document_confidence: float,
    threshold: float | None = None,
) -> tuple[bool, str]:
    """
    Determine if summary generation is allowed given document OCR confidence.

    Returns:
        (eligible, reason)
        - eligible: True if summary can be generated.
        - reason: Short message for UI (e.g. "OK", "Low OCR confidence").
    """
    if not getattr(settings, "OCR_SUMMARY_GATE_ENABLED", True):
        return True, "OK"
    min_conf = threshold if threshold is not None else getattr(
        settings, "OCR_MIN_DOCUMENT_CONFIDENCE", 0.5
    )
    if document_confidence >= min_conf:
        return True, "OK"
    return False, "Summary reliability may be degraded due to low document quality (OCR)."
