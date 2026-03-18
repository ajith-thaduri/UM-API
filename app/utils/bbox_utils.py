"""Bounding-box utilities for precise PDF term highlighting.

Two public helpers:

* assign_words_to_chunk(chunk_text, text_segments)
    Given a page's word segments and a chunk's text, returns only the word
    segments that belong to this chunk (greedy left-to-right match).

* find_term_bbox(term, word_segments)
    Given a search term and a list of word segments, returns the tight union
    bbox that covers exactly the words making up that term.  Returns None if
    the term cannot be found.

Word-segment format (same as pdfplumber output reshaped by pdf_service):
    {"text": str, "bbox": {"x0": float, "y0": float, "x1": float, "y1": float}}
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

_MAX_WINDOW_WORDS = 20  # maximum words in a single clinical term


def assign_words_to_chunk(
    chunk_text: str,
    text_segments: List[Dict],
) -> List[Dict]:
    """Return the subset of page word-segments that appear inside *chunk_text*.

    Uses a greedy sequential scan so that if the same word appears multiple
    times on a page the correct occurrence (the one inside the chunk) is
    picked rather than an earlier one that belongs to a different chunk.

    Args:
        chunk_text: The plain text of this chunk (from DocumentChunk.chunk_text).
        text_segments: Full list of word-level dicts for the page, in reading order.

    Returns:
        A new list containing only the segments whose text was found inside
        chunk_text (in order).  Segments without a "bbox" key are skipped.
    """
    if not chunk_text or not text_segments:
        return []

    chunk_lower = chunk_text.lower()
    assigned: List[Dict] = []
    search_from = 0  # advance pointer to avoid re-matching earlier occurrences

    for seg in text_segments:
        word = seg.get("text", "")
        if not word or not seg.get("bbox"):
            continue

        word_lower = word.lower()
        idx = chunk_lower.find(word_lower, search_from)
        if idx != -1:
            # Keep only {text, bbox} — compact for DB storage
            assigned.append({"text": seg["text"], "bbox": seg["bbox"]})
            search_from = idx + len(word_lower)

    return assigned


def find_term_bbox(
    term: str,
    word_segments: List[Dict],
) -> Optional[Dict[str, float]]:
    """Return the tight bounding box that covers *term* inside *word_segments*.

    For each candidate end word, the algorithm expands backwards (right-to-left)
    until the accumulated phrase contains the search term.  This ensures only
    the minimal word span that spells out the term is returned, giving a precise
    highlight rectangle rather than a coarse chunk-union bbox.

    Args:
        term: The extracted clinical term to locate (e.g. "Metformin 500mg").
        word_segments: Word-level dicts with "text" and "bbox" keys.

    Returns:
        {"x0": float, "y0": float, "x1": float, "y1": float} or None.
    """
    if not term or not word_segments:
        return None

    term_lower = term.strip().lower()
    if not term_lower:
        return None

    # Filter to segments that have both text and bbox
    words = [
        seg for seg in word_segments
        if seg.get("text") and seg.get("bbox")
    ]
    if not words:
        return None

    n = len(words)

    # For each possible end position, expand leftward to find the smallest
    # window ending at that position that contains term_lower.
    for end in range(n):
        accumulated = ""
        for start in range(end, max(-1, end - _MAX_WINDOW_WORDS), -1):
            w_text = words[start]["text"]
            accumulated = (w_text + " " + accumulated).strip() if accumulated else w_text

            if term_lower in accumulated.lower():
                # Minimal span [start..end] contains the term — union bbox
                bboxes = [words[i]["bbox"] for i in range(start, end + 1)]
                return {
                    "x0": min(b["x0"] for b in bboxes),
                    "y0": min(b["y0"] for b in bboxes),
                    "x1": max(b["x1"] for b in bboxes),
                    "y1": max(b["y1"] for b in bboxes),
                }

    return None
