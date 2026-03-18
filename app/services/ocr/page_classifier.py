"""Detect whether a page needs OCR (native text too short or missing)."""

from __future__ import annotations

import logging
from typing import List

logger = logging.getLogger(__name__)

# Minimum character count for a page to be considered "native text sufficient"
MIN_NATIVE_CHARS = 50


def page_needs_ocr(
    page_text: str,
    text_segments: List[dict],
) -> bool:
    """
    Return True if this page should be sent to OCR (e.g. scanned/image-only).

    Uses heuristics: very short text or no word-level segments suggest image-only.
    """
    text_stripped = (page_text or "").strip()
    # Placeholder text from current pdf_service
    if "[Page" in text_stripped and "may require OCR]" in text_stripped:
        return True
    if len(text_stripped) < MIN_NATIVE_CHARS:
        return True
    if not text_segments or len(text_segments) < 3:
        return True
    return False
