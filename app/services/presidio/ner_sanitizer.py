"""
presidio/ner_sanitizer.py
━━━━━━━━━━━━━━━━━━━━━━━━━
NER result quality gate and overlap resolution.

Two public functions:
  sanitize_ner_results       — 5-rule quality filter applied before tokenisation
  resolve_overlapping_spans  — 'Longest Wins' with LOCATION-over-PERSON tiebreak
"""

import re
from typing import Any, List

from app.utils.safe_logger import get_safe_logger
from .constants import (
    NER_EXACT_BLOCKLIST, NER_PHRASE_BLOCKLIST, FIELD_LABEL_STOP_WORDS,
    _PHONE_REGEX, _STREET_REGEX, _CLINICAL_CONTEXT_WORDS,
    _MAX_ENTITY_SPAN, _MIN_ENTITY_CHARS,
    _SUFFIX_ONLY_REGEX, _CREDENTIALS_TRIM_REGEX, _HONORIFIC_PREFIX_REGEX,
    _MAX_SPAN_BY_TYPE, _DEFAULT_MAX_SPAN,
)

safe_logger = get_safe_logger(__name__)


def sanitize_ner_results(results: List[Any], text: str) -> List[Any]:
    """
    Single authoritative validation gate for all NER detections.

    Rules applied (in order):
      1. Blocklist check (exact + phrase)
      2. PHONE_NUMBER disambiguation
      3. STREET_ADDRESS / clinical-word filter
      4. Email-overlapping PERSON filter
      5. PATIENT_FULL_NAME field-label filter
      6. Max-span size filter
      7. LOCATION trimming & credential disambiguation
      8. PERSON honorific/credential trimming
      9. Short-span discard
     10. Single-word low-score PERSON filter
    """
    if not results:
        return []

    zip_spans = {
        (r.start, r.end)
        for r in results
        if r.entity_type in ("ZIP_CODE", "VEHICLE_PLATE", "PASSPORT", "DRIVERS_LICENSE", "NPI")
    }
    email_spans = [r for r in results if r.entity_type == "EMAIL_ADDRESS"]

    sanitized = []
    for res in results:
        span_text = text[res.start:res.end]
        entity_type = res.entity_type

        # ── 1. Block-list ──────────────────────────────────────────────────────
        clean_entity = span_text.lower().strip(" :.,")
        if clean_entity in NER_EXACT_BLOCKLIST:
            safe_logger.debug(f"Dropping {entity_type} '{span_text}' — exact blocklist")
            continue
        blocked_phrase = any(
            re.search(rf"\b{re.escape(b)}\b", span_text, re.IGNORECASE)
            for b in NER_PHRASE_BLOCKLIST
        )
        if blocked_phrase:
            safe_logger.debug(f"Dropping {entity_type} '{span_text}' — phrase blocklist")
            continue

        # ── 2. Phone disambiguation ────────────────────────────────────────────
        if entity_type == "PHONE_NUMBER":
            if (res.start, res.end) in zip_spans:
                continue
            clean = re.sub(r"\s+", " ", span_text.strip())
            if not _PHONE_REGEX.match(clean):
                continue
            if len(span_text) > 20:
                continue

        # ── 3. Street / clinical-word filter ──────────────────────────────────
        if entity_type in ("STREET_ADDRESS", "ADDRESS"):
            _BARE_STREET = re.compile(
                r"\b(?:on|at|off|near)\s+\w.*?(?:Street|St|Avenue|Ave|Road|Rd|Blvd|Lane|Ln|Drive|Dr|Place|Pl)\b",
                re.IGNORECASE,
            )
            if not (_STREET_REGEX.match(span_text.strip()) or _BARE_STREET.search(span_text)):
                continue
            if set(span_text.lower().split()) & _CLINICAL_CONTEXT_WORDS:
                continue

        # ── 4. Email-overlapping PERSON ────────────────────────────────────────
        if entity_type == "PERSON":
            if "@" in span_text:
                continue
            if any(not (res.end <= e.start or res.start >= e.end) for e in email_spans):
                continue
            if "\n" in span_text or "\\n" in span_text:
                continue

        # ── 5. PATIENT_FULL_NAME field-label filter ────────────────────────────
        if entity_type == "PATIENT_FULL_NAME":
            clean_lower = span_text.lower().strip(" :.\n")
            if clean_lower in NER_EXACT_BLOCKLIST:
                continue
            if ":" in span_text:
                continue
            if "\n" in span_text or "\\n" in span_text:
                continue

        # ── 6. Max span ────────────────────────────────────────────────────────
        max_span = _MAX_SPAN_BY_TYPE.get(entity_type, _DEFAULT_MAX_SPAN)
        if (res.end - res.start) > max_span:
            safe_logger.debug(f"Dropping oversized {entity_type} span ({res.end - res.start} chars)")
            continue

        # ── 7. LOCATION: trim newline-prefix / credential disambiguation ───────
        if entity_type in ("LOCATION", "CITY", "CITY_FACILITY", "STREET_ADDRESS"):
            if re.match(r"^\d+$", span_text.strip()):
                continue
            if re.search(r"\b\d{1,2}\s*(?:AM|PM)\b", span_text, re.IGNORECASE):
                continue
            if "\n" in span_text:
                last_nl = span_text.rfind("\n")
                trimmed = span_text[last_nl + 1:].strip()
                if trimmed:
                    res.start = (
                        res.start + last_nl + 1
                        + (len(span_text[last_nl + 1:]) - len(span_text[last_nl + 1:].lstrip()))
                    )
                    span_text = text[res.start:res.end]

            if _CREDENTIALS_TRIM_REGEX.search(span_text):
                is_cred = False
                prefix_end = span_text.find(",")
                if prefix_end != -1:
                    prefix = span_text[:prefix_end].strip()
                    for other in results:
                        if (
                            other.entity_type == "PERSON"
                            and other.start == res.start
                            and other.end == res.start + prefix_end
                        ):
                            is_cred = True
                            break
                    if not is_cred:
                        multi_word = len(re.findall(r"[A-Z][a-z]+", prefix)) >= 2
                        medical_only = re.search(
                            r"\b(?:PhD|FACS|FACC|FCCP|RN|LPN|PGY-\d)\b", span_text, re.IGNORECASE
                        )
                        if multi_word or medical_only:
                            is_cred = True
                if is_cred:
                    safe_logger.debug(f"Dropping {entity_type} '{span_text}' — credential pattern")
                    continue

        # ── 8. PERSON: trim honorific prefix and credential suffix ─────────────
        if entity_type == "PERSON":
            pre = _HONORIFIC_PREFIX_REGEX.match(span_text)
            if pre:
                res.start += pre.end()
                span_text = text[res.start:res.end]
            suf = _CREDENTIALS_TRIM_REGEX.search(span_text)
            if suf:
                res.end = res.start + suf.start()
                span_text = text[res.start:res.end]

        # ── 9. Short span ──────────────────────────────────────────────────────
        clean_span = span_text.strip(" ,.() ")
        if len(clean_span) < _MIN_ENTITY_CHARS or _SUFFIX_ONLY_REGEX.match(span_text):
            continue

        # ── 10. Single-word low-score PERSON ──────────────────────────────────
        if entity_type == "PERSON" and " " not in span_text.strip():
            if res.score < 0.90:
                continue

        # ── 11. Field-label stop-word filter ─────────────────────────────────
        if entity_type == "PERSON":
            words = set(re.findall(r"\w+", span_text.lower()))
            if words and words.issubset(FIELD_LABEL_STOP_WORDS):
                safe_logger.debug(f"Dropping PERSON '{span_text}' — looks like a field label")
                continue

        sanitized.append(res)

    return sanitized


def resolve_overlapping_spans(results: List[Any]) -> List[Any]:
    """
    'Longest Wins' strategy.
    Tiebreak: LOCATION-family beats PERSON-family (prevents city names being tokenised as persons).
    """
    if not results:
        return []

    TYPE_PRIORITY = {
        "CITY_FACILITY": 0, "LOCATION": 0, "CITY": 0, "STREET_ADDRESS": 0,
        "MAC_ADDRESS": 0, "IP_ADDRESS": 0, "COORDINATE": 0, "ZIP_CODE": 0,
        "EMAIL_ADDRESS": 1, "PHONE_NUMBER": 1, "URL": 1,
        "ID": 2, "SSN": 2, "MRN": 2,
        "ORGANIZATION": 3, "HOSPITAL": 3,
        "PERSON": 4, "PATIENT_FULL_NAME": 5,
    }

    def sort_key(x):
        length = x.end - x.start
        priority = TYPE_PRIORITY.get(x.entity_type, 3)
        return (-length, priority, -x.score)

    sorted_results = sorted(results, key=sort_key)
    final: List[Any] = []
    for res in sorted_results:
        if not any(not (res.end <= k.start or res.start >= k.end) for k in final):
            final.append(res)

    return sorted(final, key=lambda x: x.start)
