"""
app/services/presidio/__init__.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Public API for the presidio de-identification package.

All existing import paths are preserved for full backward compatibility:

  # All callers continue to work unchanged:
  from app.services.presidio_deidentification_service import (
      presidio_deidentification_service,
      PresidioDeIdentificationService,
      normalize_entity_type,
  )

  from app.services.presidio_recognizers import MRNRecognizer, ...
"""

# ── Core service class & singleton ────────────────────────────────────────────
from .service import PresidioDeIdentificationService, presidio_deidentification_service

# ── Utility re-exports ────────────────────────────────────────────────────────
from .constants import normalize_entity_type

# ── Sub-module public symbols (for direct imports if needed) ──────────────────
from .recognizers import ALL_RECOGNIZERS
from .phi_collector import collect_known_phi, generate_tokens
from .ner_sanitizer import sanitize_ner_results, resolve_overlapping_spans
from .span_processor import process_residual_phi_in_string, presidio_scan_free_text
from .date_handler import shift_dates_structured, shift_dates_in_text

__all__ = [
    # Primary public API
    "presidio_deidentification_service",
    "PresidioDeIdentificationService",
    "normalize_entity_type",
    # Sub-module helpers (rarely needed externally)
    "ALL_RECOGNIZERS",
    "collect_known_phi",
    "generate_tokens",
    "sanitize_ner_results",
    "resolve_overlapping_spans",
    "process_residual_phi_in_string",
    "presidio_scan_free_text",
    "shift_dates_structured",
    "shift_dates_in_text",
]
