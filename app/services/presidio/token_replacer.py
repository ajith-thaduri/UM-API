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

    # ── Stage 1: Heuristic Regex Strip ───────────────────────────────────────
    result = re.sub(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", "[[REDACTED]]", result)
    result = re.sub(r"https?://[^\s<>\"]+|www\.[^\s<>\"]+", "[[REDACTED]]", result)
    result = re.sub(r"(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}", "[[REDACTED]]", result)
    # SSN
    result = re.sub(r"\b\d{3}-\d{2}-\d{4}\b", "[[REDACTED]]", result)
    # MAC Address
    result = re.sub(r"\b([0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b", "[[REDACTED]]", result)
    # IPv4
    result = re.sub(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", "[[REDACTED]]", result)
    # Credit Cards
    result = re.sub(r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b", "[[REDACTED]]", result)
    # VIN
    result = re.sub(r"\b[A-HJ-NPR-Z0-9]{17}\b", "[[REDACTED]]", result)
    # Country names
    for country in ["United States", "USA", "U.S.", "U.S.A.", "United Kingdom", "UK"]:
        result = re.sub(r"\b" + re.escape(country) + r"\b", "[[REDACTED]]", result, flags=re.I)
    # Vehicle plates (common format)
    result = re.sub(r"\b[A-Z]{2}-[A-Z]{2,4}-\d{4}\b", "[[REDACTED]]", result)
    # Passport / Driver's License (contextual)
    result = re.sub(r"\b(?:Passport|License|DL)[:\s]*[A-Z]\d{6,9}\b", "[[REDACTED]]", result, flags=re.I)
    # Sub-addresses
    result = re.sub(r"\bAp(?:art)?(?:ment|t)?\.?\s*#?\s*\w{1,6}\b", "[[REDACTED]]", result, flags=re.I)
    result = re.sub(r"\bS(?:ui)?te\.?\s*#?\s*\w{1,6}\b", "[[REDACTED]]", result, flags=re.I)
    result = re.sub(r"\bR(?:oo)?m\.?\s*#?\s*\d{1,4}[A-Za-z]?\b", "[[REDACTED]]", result, flags=re.I)
    result = re.sub(r"\bUnit\s*#?\s*\w{1,6}\b", "[[REDACTED]]", result, flags=re.I)
    # City, State (full state names)
    result = re.sub(
        rf"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){{0,2}},\s*(?:{_US_STATE_FULL})\b",
        "[[REDACTED]]", result
    )
    # Ages ≥ 90
    result = re.sub(r"\b(\d{1,3})\s*years?\s*old\b", _redact_age_90plus, result, flags=re.IGNORECASE)

    # ── Stage 2: Known PHI / Identity Replacement ─────────────────────────────
    replacements: List[tuple] = []
    for s in strip_list:
        if s and len(s) > 3:
            replacements.append((s, "[[REDACTED]]"))
    for val, token in variant_token_map.items():
        if val and len(val) > 2:
            replacements.append((val, token))
    # Longest-first so overlapping strings don't partially clobber each other
    replacements.sort(key=lambda x: len(x[0]), reverse=True)

    for original, target in replacements:
        if original in result:
            if target == "[[REDACTED]]":
                result = re.sub(re.escape(original), target, result, flags=re.IGNORECASE)
            else:
                result = re.sub(
                    r"\b" + re.escape(original) + r"\b", target, result, flags=re.IGNORECASE
                )

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
