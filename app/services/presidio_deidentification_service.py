"""
app/services/presidio_deidentification_service.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BACKWARD-COMPATIBILITY SHIM
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
This file has been refactored into the modular package:

    app/services/presidio/
    ├── __init__.py       ← package API
    ├── constants.py      ← entity maps, blocklists, tiers
    ├── recognizers.py    ← all custom PatternRecognizers
    ├── engine.py         ← NLP engine lifecycle
    ├── phi_collector.py  ← known-PHI collection & tokenisation
    ├── token_replacer.py ← regex + deterministic replacement
    ├── ner_sanitizer.py  ← NER quality gate + overlap resolution
    ├── span_processor.py ← TOKENIZE/STRIP/DATE tier application
    ├── date_handler.py   ← date shifting / reversal
    └── service.py        ← thin orchestrator (~220 lines)

This shim re-exports every previously public symbol so that all
existing callers continue to work without modification.
"""

# Re-export everything from the new package
from app.services.presidio import (                              # noqa: F401
    presidio_deidentification_service,
    PresidioDeIdentificationService,
    normalize_entity_type,
)

# Also re-export constants that some callers may import directly
from app.services.presidio.constants import (                   # noqa: F401
    ROBERTA_LABEL_TO_PRESIDIO,
    ENTITY_TYPE_NORMALIZATION,
    NER_EXACT_BLOCKLIST,
    NER_PHRASE_BLOCKLIST,
    TOKENIZE_TYPES,
    STRIP_TYPES,
    KNOWN_PHI_FIELDS,
    FREE_TEXT_FIELDS,
    DATE_FIELD_KEYWORDS,
    NER_MODEL_REGISTRY,
    ENTITY_PRIORITY,
    normalize_entity_type,
)
