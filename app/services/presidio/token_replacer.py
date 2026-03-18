"""
presidio/token_replacer.py
━━━━━━━━━━━━━━━━━━━━━━━━━━
Known-PHI replacement in both structured data and free-text strings.

Stage 1 — Heuristic / regex strips (emails, phones, MAC, IPv4, …)
Stage 2 — Deterministic identity replacement (longest-first)
"""

import re
from typing import Any, Dict, List
from app.utils.safe_logger import get_safe_logger

safe_logger = get_safe_logger(__name__)

# US state abbreviations used in the city-state pattern
_US_STATE_FULL = (
    r"Alabama|Alaska|Arizona|Arkansas|California|Colorado|Connecticut|Delaware|"
    r"Florida|Georgia|Hawaii|Idaho|Illinois|Indiana|Iowa|Kansas|Kentucky|Louisiana|"
    r"Maine|Maryland|Massachusetts|Michigan|Minnesota|Mississippi|Missouri|Montana|"
    r"Nebraska|Nevada|New\s+Hampshire|New\s+Jersey|New\s+Mexico|New\s+York|"
    r"North\s+Carolina|North\s+Dakota|Ohio|Oklahoma|Oregon|Pennsylvania|"
    r"Rhode\s+Island|South\s+Carolina|South\s+Dakota|Tennessee|Texas|Utah|Vermont|"
    r"Virginia|Washington|West\s+Virginia|Wisconsin|Wyoming"
)


def _redact_age_90plus(m: re.Match) -> str:
    try:
        return "90+ years old" if int(m.group(1)) >= 90 else m.group(0)
    except (ValueError, IndexError):
        return m.group(0)


def replace_in_string(
    text: str,
    variant_token_map: Dict[str, str],
    strip_list: List[str],
) -> str:
    """
    Single-string PHI replacement pipeline.

    Stage 1: High-confidence regex strips (email, URL, phone, SSN, MAC, …)
    Stage 2: Known identity / strip replacement (longest-first)
    """
    if not text:
        return text

    result = text

    # ── Stage 1: Heuristic Regex Strip (HIPAA Safe Harbor only) ─────────────

    # 1. Email addresses — unambiguous
    result = re.sub(r"\b[a-zA-Z0-9._%+-]+@(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}\b", "[[REDACTED]]", result)

    # 2. URLs / web addresses — unambiguous
    result = re.sub(r"\b(?:https?://|www\.)[^\s<>\"]+\b", "[[REDACTED]]", result)

    # 3. US phone numbers — must match full US phone format (10+ digits with separators)
    #    Tightened: requires area code + 7 digit number with explicit separators
    result = re.sub(
        r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}\b",
        "[[REDACTED]]", result
    )

    # 4. SSN — unambiguous format
    result = re.sub(r"\b\d{3}-\d{2}-\d{4}\b", "[[REDACTED]]", result)

    # 5. MAC Address
    result = re.sub(r"\b([0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b", "[[REDACTED]]", result)

    # 6. IPv4 — only redact when all 4 octets are in valid IP range (0-255)
    def _is_valid_ipv4(m):
        parts = m.group().split(".")
        if all(0 <= int(p) <= 255 for p in parts):
            return "[[REDACTED]]"
        return m.group()
    result = re.sub(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", _is_valid_ipv4, result)

    # 7. Credit Card numbers (4 groups of 4 digits)
    result = re.sub(r"\b\d{4}[-\s]\d{4}[-\s]\d{4}[-\s]\d{4}\b", "[[REDACTED]]", result)

    # 8. Ages ≥ 90 only
    result = re.sub(r"\b(\d{1,3})\s*years?\s*old\b", _redact_age_90plus, result, flags=re.IGNORECASE)


    # ── Stage 2: Known PHI / Identity Replacement ─────────────────────────────
    replacements: List[tuple] = []
    
    # Only add strips that are reasonably long/specific to avoid accidental word redaction
    for s in strip_list:
        if s and len(str(s).strip()) > 4:
            replacements.append((str(s).strip(), "[[REDACTED]]"))
            
    for val, token in variant_token_map.items():
        if val and len(str(val).strip()) > 3: # Ignore variants <= 3 chars
            replacements.append((str(val).strip(), token))
            
    # Longest-first so overlapping strings don't partially clobber each other
    replacements.sort(key=lambda x: len(x[0]), reverse=True)

    for original, target in replacements:
        pattern = re.escape(original)
        if target != "[[REDACTED]]":
            pattern = r"\b" + pattern + r"\b"
            
        result = re.sub(pattern, target, result, flags=re.IGNORECASE)

    return result


def replace_known_phi(
    data: Any,
    variant_token_map: Dict[str, str],
    strip_list: List[str],
) -> Any:
    """Recursively replace known PHI in structured data (dicts / lists / strings)."""
    if isinstance(data, dict):
        return {k: replace_known_phi(v, variant_token_map, strip_list) for k, v in data.items()}
    elif isinstance(data, list):
        return [replace_known_phi(item, variant_token_map, strip_list) for item in data]
    elif isinstance(data, str):
        return replace_in_string(data, variant_token_map, strip_list)
    return data
