"""
presidio/span_processor.py
━━━━━━━━━━━━━━━━━━━━━━━━━━
Processes individual text spans after NER detection — applies
the TOKENIZE, STRIP, DATE, and AGE tiers to produce the final
de-identified string.

Public entry-points:
  process_residual_phi_in_string — full pipeline (sanitize → resolve → apply)
  process_single_string          — wrapper for free-text field scanning
"""

import re
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.utils.safe_logger import get_safe_logger
from .constants import (
    TOKENIZE_TYPES, STRIP_TYPES, normalize_entity_type, FREE_TEXT_FIELDS
)
from .ner_sanitizer import sanitize_ner_results, resolve_overlapping_spans

safe_logger = get_safe_logger(__name__)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _shift_dates_in_text(text: str, shift_days: int) -> str:
    """Delegate to the project-level date shift service."""
    if not text or shift_days == 0:
        return text
    from app.services.date_shift_service import shift_dates_in_text
    return shift_dates_in_text(text, shift_days, direction=1)


def _overlaps_any_token(r_s: int, r_e: int, token_spans: list) -> bool:
    return any(not (r_e <= ts or r_s >= te) for ts, te in token_spans)


# ── Public functions ──────────────────────────────────────────────────────────

def process_residual_phi_in_string(
    text: str,
    analyzer_results: List[Any],
    token_map: Dict[str, str],
    shift_days: int = 0,
    score_threshold: float = 0.85,
) -> str:
    """
    Process NER-detected entities not caught by the deterministic stage.

    Pipeline:
      1. Sanitize (10-rule NER quality gate)
      2. Resolve overlapping spans (Longest Wins)
      3. Threshold filter
      4. Apply tiers right-to-left: DATE → AGE → ZIP → STRIP → TOKENIZE
      5. Post-processing consolidation
    """
    if not analyzer_results:
        return text

    # 1. Sanitize
    filtered = sanitize_ner_results(analyzer_results, text)

    # 2. Resolve overlaps
    filtered = resolve_overlapping_spans(filtered)

    # 3. Threshold filter
    def passes_threshold(res):
        entity_type = normalize_entity_type(res.entity_type)
        floor = min(score_threshold, 0.80) - 0.005 if entity_type == "LOCATION" else score_threshold - 0.005
        return res.score >= floor

    filtered = [res for res in filtered if passes_threshold(res)]

    # 4. Apply replacements END → START (reverse order preserves offsets)
    filtered.sort(key=lambda x: x.start, reverse=True)

    new_text = text
    for res in filtered:
        raw_type = res.entity_type
        entity_type = normalize_entity_type(raw_type)
        entity_text = new_text[res.start:res.end].strip()
        if not entity_text or len(entity_text) < 2:
            continue

        # TIER C: DATE — safety-shift residual dates
        if entity_type == "DATE_TIME":
            # If it's already in MM/DD/YYYY format, it's likely already shifted by a previous pass
            # (e.g. the global shift_dates_in_text called before this). Skip to avoid double-shifting.
            if re.match(r"^\d{1,2}/\d{1,2}/\d{4}$", entity_text):
                continue
            shifted = _shift_dates_in_text(entity_text, shift_days)
            new_text = new_text[:res.start] + shifted + new_text[res.end:]
            continue

        # TIER D: AGE — redact ages ≥ 90 only
        if entity_type == "AGE":
            try:
                m = re.search(r"\d+", entity_text)
                if m and int(m.group()) >= 90:
                    new_text = new_text[:res.start] + "90+" + new_text[res.end:]
            except (ValueError, AttributeError):
                pass
            continue

        # IPv4 masquerading as ID
        if entity_type == "ID" and re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", entity_text):
            entity_type = "IP_ADDRESS"

        # TIER B: ZIP — HIPAA mask (e.g. 62704 → 627**)
        if raw_type == "ZIP_CODE":
            masked = entity_text[:3] + "**" if len(entity_text) >= 3 else "**"
            new_text = new_text[:res.start] + masked + new_text[res.end:]
            continue

        # TIER B: STRIP
        if entity_type in STRIP_TYPES or "@" in entity_text:
            new_text = new_text[:res.start] + "[[REDACTED]]" + new_text[res.end:]
            continue

        # TIER A: TOKENIZE
        if entity_type not in TOKENIZE_TYPES:
            new_text = new_text[:res.start] + "[[REDACTED]]" + new_text[res.end:]
            continue

        existing_token = next(
            (tok for tok, val in token_map.items() if val == entity_text), None
        )
        if not existing_token:
            max_idx = 0
            prefix = f"[[{entity_type}-"
            for tok in token_map:
                if tok.startswith(prefix):
                    m2 = re.search(rf"\[\[{entity_type}-(\d+)\]\]", tok)
                    if m2:
                        idx = int(m2.group(1))
                        if idx > max_idx:
                            max_idx = idx
            existing_token = f"[[{entity_type}-{max_idx + 1:02d}]]"
            token_map[existing_token] = entity_text

        new_text = new_text[:res.start] + existing_token + new_text[res.end:]

    # 5. Post-processing
    # Remove trailing hospital suffix from org tokens
    new_text = re.sub(
        r"(\[\[[A-Z_]+-\d{2,}\]\])\s+(?:Hospital|Medical Center|Clinic|Health Center|Health System)",
        r"\1", new_text
    )
    # Consolidate adjacent [[REDACTED]] tokens
    new_text = re.sub(r"(\[\[REDACTED\]\]\s*)+", "[[REDACTED]] ", new_text).strip()

    return new_text


def process_single_string(
    parent_obj: Any,
    key: Any,
    text: str,
    analyzer: Any,
    token_map: Dict[str, str],
    shift_days: int = 0,
    score_threshold: Optional[float] = None,
) -> None:
    """
    Analyse a single free-text field and write the de-identified value back
    into parent_obj[key].
    """
    if score_threshold is None:
        score_threshold = settings.PRESIDIO_FREE_TEXT_THRESHOLD
    if not analyzer:
        return

    try:
        results = analyzer.analyze(text=text, language="en", score_threshold=score_threshold)
        if not results:
            return

        results = sanitize_ner_results(results, text)

        # Filter spans that already contain a token marker
        token_markers = [(m.start(), m.end()) for m in re.finditer(r"\[\[.*?\]\]", text)]
        results = [r for r in results if not _overlaps_any_token(r.start, r.end, token_markers)]

        if not results:
            return

        parent_obj[key] = process_residual_phi_in_string(
            text, results, token_map, shift_days, score_threshold
        )
    except Exception as e:
        safe_logger.warning(f"Presidio scan failed for field '{key}': {e}")


def presidio_scan_free_text(
    data: Any,
    analyzer: Any,
    token_map: Dict[str, str],
    shift_days: int = 0,
    score_threshold: Optional[float] = None,
) -> Any:
    """
    Recursively scan free-text fields in structured data with Presidio.
    Only fields whose key is in FREE_TEXT_FIELDS are scanned.
    """
    if score_threshold is None:
        score_threshold = settings.PRESIDIO_FREE_TEXT_THRESHOLD
    if not analyzer:
        return data

    def _scan(obj):
        if isinstance(obj, dict):
            for key, value in obj.items():
                if isinstance(value, str) and key.lower() in FREE_TEXT_FIELDS:
                    process_single_string(obj, key, value, analyzer, token_map, shift_days, score_threshold)
                elif isinstance(value, (dict, list)):
                    _scan(value)
        elif isinstance(obj, list):
            for item in obj:
                _scan(item)

    _scan(data)
    return data
