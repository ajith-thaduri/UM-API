"""
presidio/date_handler.py
━━━━━━━━━━━━━━━━━━━━━━━━
All date-shifting logic: structured data traversal, single-field shift,
and best-effort reversal for re-identification.
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from app.utils.safe_logger import get_safe_logger
from .constants import DATE_FIELD_KEYWORDS

safe_logger = get_safe_logger(__name__)


def is_date_field(field_name: str) -> bool:
    """Return True if field name suggests it contains a date value."""
    field_lower = field_name.lower()
    return any(kw in field_lower for kw in DATE_FIELD_KEYWORDS)


def shift_single_date(date_str: str, shift_days: int) -> str:
    """Shift a single date string. Returns original if unparseable or redaction if strict DD/MM."""
    from app.utils.date_utils import is_strict_dd_mm_yyyy
    if is_strict_dd_mm_yyyy(date_str):
        return "[[REDACTED]]"

    for fmt in ["%Y-%m-%d", "%m/%d/%Y", "%Y-%m-%d %H:%M:%S"]:
        try:
            dt = datetime.strptime(date_str, fmt)
            return (dt + timedelta(days=shift_days)).strftime(fmt)
        except ValueError:
            continue
    return date_str


def shift_dates_in_text(text: str, shift_days: int) -> str:
    """Shift all recognisable dates in free-text using the project date-shift service."""
    if not text or shift_days == 0:
        return text
    from app.services.date_shift_service import shift_dates_in_text as _svc_shift
    return _svc_shift(text, shift_days, direction=1)


def reverse_dates_in_text(text: str, shift_days: int) -> str:
    """Best-effort reversal of shifted dates in narrative text."""
    if shift_days == 0:
        return text
    from app.services.date_shift_service import date_shift_service
    return date_shift_service.reidentify_summary_text(text, shift_days)


def shift_dates_structured(
    data: Any, shift_days: int, path: str = ""
) -> Tuple[Any, List[Dict]]:
    """
    Recursively shift dates in structured data with field-path tracking.

    Returns:
        (shifted_data, shifted_fields)
        shifted_fields = [{'path': ..., 'original': ..., 'shifted': ...}, ...]
    """
    shifted_fields: List[Dict] = []

    def _recurse(obj, current_path):
        if isinstance(obj, dict):
            result = {}
            for key, value in obj.items():
                field_path = f"{current_path}.{key}" if current_path else key
                if is_date_field(key) and isinstance(value, str):
                    shifted_value = shift_single_date(value, shift_days)
                    if shifted_value != value:
                        shifted_fields.append(
                            {"path": field_path, "original": value, "shifted": shifted_value}
                        )
                    result[key] = shifted_value
                elif isinstance(value, str):
                    # For non-date fields, still perform a regex-based shift for any dates within the text
                    result[key] = shift_dates_in_text(value, shift_days)
                else:
                    result[key] = _recurse(value, field_path)
            return result
        elif isinstance(obj, list):
            return [_recurse(item, f"{current_path}[{i}]") for i, item in enumerate(obj)]
        elif isinstance(obj, str):
            return shift_dates_in_text(obj, shift_days)
        return obj

    shifted_data = _recurse(data, path)
    return shifted_data, shifted_fields
