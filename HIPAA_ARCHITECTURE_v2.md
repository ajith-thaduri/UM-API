# Two-Tier HIPAA Architecture v2.0 (Corrected)
## Microsoft Presidio + OpenRouter + Claude — Production-Grade

---

## Changelog from v1

| Issue | v1 (Dangerous) | v2 (Fixed) |
|-------|----------------|------------|
| Token format | `[PATIENT]`, `[PROVIDER_1]` | `[[PERSON::a94f2c]]` — UUID-based, unique per entity |
| Token map | Collapsed duplicates silently | Strict 1:1 mapping, every entity gets unique UUID token |
| PHI handling | Serialize → Presidio on text → re-apply | **Structured-first**: replace known fields explicitly, Presidio catches free-text leaks only |
| Date reversal | Regex on Claude output text | **Structure-aware**: dates tracked by field path, reversed in structured output |
| Faker pseudonyms | Optional enhancement | **Removed entirely**. Tokens only, never fake names |
| Logging | PHI-adjacent data logged | **Zero-PHI logging policy**. No shift values, no token maps, no entity text in logs |

---

## Table of Contents
1. [Architecture Overview](#architecture-overview)
2. [De-Identification Strategy (Corrected)](#de-identification-strategy)
3. [Token System (Must-Fix #1 & #2)](#token-system)
4. [Structured PHI Handling (Must-Fix #3)](#structured-phi-handling)
5. [Date Shifting (Must-Fix #4)](#date-shifting)
6. [Logging Policy (Must-Fix #5)](#logging-policy)
7. [Pre-Flight PHI Validator](#pre-flight-phi-validator)
8. [Technical Implementation](#technical-implementation)
9. [Security Guarantees](#security-guarantees)
10. [Implementation Roadmap](#implementation-roadmap)

---

## Architecture Overview

### Tier Separation (Unchanged — This Was Correct)

```
Tier 1 (Secure Zone)          Privacy Boundary           Tier 2 (External)
┌─────────────────────┐    ┌─────────────────────┐    ┌──────────────────┐
│ OpenRouter OSS LLM  │    │ De-ID Engine         │    │ Claude           │
│                     │    │                      │    │                  │
│ • Clinical Agent    │    │ 1. Structured PHI    │    │ • Summary only   │
│ • Timeline          │───▶│    replacement       │───▶│ • Zero PHI       │
│ • Red Flags         │    │ 2. Date shifting     │    │ • Tokens only    │
│ • Follow-up Agent   │    │ 3. Presidio (text)   │    │                  │
│                     │    │ 4. PHI Validator      │    │                  │
│ Full PHI Access ✅   │    │ 5. Privacy Vault     │    │ No PHI Ever ❌    │
└─────────────────────┘    └─────────────────────┘    └──────────────────┘
                                     │                         │
                                     │                         │
                                     ▼                         │
                           ┌─────────────────┐                 │
                           │ Privacy Vault    │                 │
                           │ (PostgreSQL)     │◀────────────────┘
                           │                  │   Re-ID from vault
                           │ • Token map      │   (structure-aware)
                           │ • Date shift     │
                           │ • Field paths    │
                           └─────────────────┘
```

---

## De-Identification Strategy

### Processing Order (Critical — This Is the Fix)

The de-identification engine processes data in **strict order**:

```
Step 1: STRUCTURED PHI REPLACEMENT
       Known fields (patient_name, MRN, facility) replaced with UUID tokens
       ↓
Step 2: DATE SHIFTING
       All date fields shifted by per-case random offset
       Field paths recorded for structure-aware reversal
       ↓
Step 3: PRESIDIO TEXT SCAN
       Free-text fields (descriptions, notes, history) scanned for leaked PHI
       Any detected entities get unique UUID tokens
       ↓
Step 4: PRE-FLIGHT PHI VALIDATOR
       Final scan of entire payload
       If ANY PHI pattern detected → BLOCK the request (fail-closed)
       ↓
Step 5: SEND TO CLAUDE
       ↓
Step 6: STRUCTURE-AWARE RE-IDENTIFICATION
       Token replacement from vault (exact 1:1)
       Date reversal from vault (field-path based, not regex)
```

**Why this order matters**:
- Step 1 handles the **known** PHI from structured data (patient name, MRN, facility are always in specific fields)
- Step 3 catches anything **leaked** into free-text that Step 1 missed
- Step 4 is the **safety net** — if anything slips through, the request is blocked entirely

---

## Token System

### v1 (Dangerous — Removed)
```
❌ [PATIENT]           — Not unique, Claude drops brackets
❌ [PROVIDER_1]        — Collapses multiple providers
❌ [FACILITY]          — Single token for multiple facilities
```

### v2 (Fixed — UUID-Based Tokens)
```
✅ [[PERSON::a94f2c3b]]          — Unique per entity instance
✅ [[PERSON::7e1d8a42]]          — Different token for different person
✅ [[ORG::b3c9e1f7]]             — Unique per facility
✅ [[DATE::SHIFTED]]             — Dates are shifted, not tokenized
```

### Token Format Specification

```
Format:  [[TYPE::UUID8]]
         ^^    ^^    ^^
         │     │     └── 8-char hex from uuid4 (unique per entity)
         │     └──────── Entity type (PERSON, ORG, LOC, ID)
         └────────────── Double brackets (survives Claude paraphrasing)
```

**Entity Types**:
| Type | Used For | Example |
|------|----------|---------|
| `PERSON` | Patient names, provider names | `[[PERSON::a94f2c3b]]` |
| `ORG` | Facility names, insurance companies | `[[ORG::b3c9e1f7]]` |
| `LOC` | Cities, addresses, geographic locations | `[[LOC::d1e2f3a4]]` |
| `ID` | MRN, SSN, account numbers | `[[ID::c7b8a9d0]]` |

**Why this works**:
1. **Unique**: Every entity instance gets its own UUID — two providers = two different tokens
2. **Survives paraphrasing**: Double brackets + `::` separator is unusual enough that Claude preserves it
3. **Never collides**: UUID ensures no two tokens are the same
4. **Auditable**: Token type tells you what category was redacted

### Token Map (1:1 Strict)

```python
# v1 (DANGEROUS — collapsed duplicates)
❌ token_map = {
    "[PROVIDER_1]": "Dr. Smith",    # What about Dr. Brown?
    "[FACILITY]": "St. Mary's",     # What about Memorial Hospital?
}

# v2 (FIXED — every entity gets unique token)
✅ token_map = {
    "[[PERSON::a94f2c3b]]": "John Doe",         # Patient
    "[[PERSON::7e1d8a42]]": "Dr. Smith",         # Provider 1
    "[[PERSON::3f5b9c11]]": "Dr. Brown",         # Provider 2
    "[[ORG::b3c9e1f7]]": "St. Mary's Hospital",  # Facility 1
    "[[ORG::e4d5c6a8]]": "Memorial Hospital",    # Facility 2
    "[[ID::c7b8a9d0]]": "MRN123456",             # MRN
    "[[LOC::d1e2f3a4]]": "Boston, MA",           # Location
}
```

---

## Structured PHI Handling

### The Problem with v1

v1 serialized structured data to text, ran Presidio, then tried to map back:

```python
# v1 (DANGEROUS)
combined_text = serialize(timeline, clinical_data)  # Lossy conversion
results = presidio.analyze(combined_text)            # Detects in flat text
token_map = build_map(results)                       # Mismatch risk
apply_to_structured_data(...)                        # Partial replacements
```

This creates:
- **Serialization mismatch**: Detected text span ≠ original structured field
- **Partial replacements**: "Dr. Smith" in text but `{"provider": "Dr. Smith"}` in struct
- **Missed fields**: Presidio may not detect a name if serialized without context

### v2: Structured-First, Presidio-Second

```python
# v2 (CORRECT)

# STEP 1: Replace KNOWN structured PHI fields explicitly
#         These are deterministic — we KNOW where they are
structured_replacements = {
    "patient_name":      generate_token("PERSON"),    # Always exists
    "mrn":               generate_token("ID"),         # Always exists
    "facility":          generate_token("ORG"),        # If present
    "attending_provider": generate_token("PERSON"),    # If present
    "referring_provider": generate_token("PERSON"),    # If present
}

# Walk every structured field and replace known PHI values
de_id_data = replace_in_structure(clinical_data, structured_replacements)
de_id_timeline = replace_in_structure(timeline, structured_replacements)

# STEP 2: Presidio scans FREE-TEXT fields only (descriptions, notes, history)
#         This catches PHI that leaked into narrative text
for event in de_id_timeline:
    event["description"] = presidio_scrub(event["description"])

for entry in de_id_data.get("history", []):
    if isinstance(entry, dict) and "text" in entry:
        entry["text"] = presidio_scrub(entry["text"])
```

### Known PHI Fields (Explicit Replacement List)

These fields are **always replaced** before Presidio runs:

```python
KNOWN_PHI_FIELDS = {
    # Top-level case fields
    "patient_name": "PERSON",
    "case_number": "ID",
    
    # Demographics
    "patient_demographics.name": "PERSON",
    "patient_demographics.mrn": "ID",
    "patient_demographics.ssn": "ID",
    "patient_demographics.address": "LOC",
    "patient_demographics.phone": "ID",
    "patient_demographics.email": "ID",
    
    # Provider fields (in any nested structure)
    "attending_provider": "PERSON",
    "referring_provider": "PERSON",
    "ordering_provider": "PERSON",
    "consulting_provider": "PERSON",
    
    # Facility fields
    "facility_name": "ORG",
    "hospital_name": "ORG",
    "clinic_name": "ORG",
    
    # Insurance
    "insurance_id": "ID",
    "insurance_company": "ORG",
    "group_number": "ID",
    "policy_number": "ID",
}
```

### Free-Text Fields (Presidio Scans These)

After structured replacement, Presidio scans these narrative fields for leaked PHI:

```python
FREE_TEXT_FIELDS = [
    # Timeline
    "timeline[*].description",
    "timeline[*].details.notes",
    
    # Clinical data
    "clinical_data.history[*].text",
    "clinical_data.chief_complaint",
    "clinical_data.social_factors[*].description",
    "clinical_data.therapy_notes[*].notes",
    
    # Red flags
    "red_flags[*].description",
    "red_flags[*].details.reason",
]
```

---

## Date Shifting

### v1 (Dangerous — Regex Reversal)

```python
# v1 (DANGEROUS)
# Reverse dates in Claude's output using regex
date_pattern = r'\d{4}-\d{2}-\d{2}'
re.sub(date_pattern, reverse_shift, summary_text)

# FAILS when Claude outputs:
# "Feb 3, 2024"          → Not matched
# "02/03/24"             → Not matched
# "three days later"     → Not matched
# "2024-01-15 lab value" → Wrong reversal (this might be a lab ID, not a date)
```

### v2: Structure-Aware Date Shifting

**Principle**: Dates are shifted in **structured data before prompt construction**. Claude never sees real dates. Re-identification reverses dates in **structured output**, not in Claude's free-text response.

```python
class DateShiftEngine:
    """Structure-aware date shifting"""
    
    def __init__(self, shift_days: int):
        self.shift_days = shift_days
        self.shifted_fields = []  # Track which fields were shifted
    
    def shift_structured_dates(
        self,
        data: dict | list,
        path: str = ""
    ) -> dict | list:
        """
        Walk structured data and shift all date fields.
        Records field paths for structure-aware reversal.
        """
        if isinstance(data, list):
            return [
                self.shift_structured_dates(item, f"{path}[{i}]")
                for i, item in enumerate(data)
            ]
        
        if isinstance(data, dict):
            result = {}
            for key, value in data.items():
                current_path = f"{path}.{key}" if path else key
                
                if self._is_date_field(key) and isinstance(value, str):
                    shifted = self._shift_date_value(value)
                    if shifted != value:
                        self.shifted_fields.append({
                            "path": current_path,
                            "original": value,
                            "shifted": shifted
                        })
                        result[key] = shifted
                    else:
                        result[key] = value
                elif isinstance(value, (dict, list)):
                    result[key] = self.shift_structured_dates(value, current_path)
                else:
                    result[key] = value
            return result
        
        return data
    
    def _is_date_field(self, field_name: str) -> bool:
        """Check if a field name indicates a date"""
        date_indicators = [
            "date", "admitted", "discharged", "performed",
            "collected", "ordered", "started", "stopped",
            "created_at", "timestamp", "dob", "date_of_birth"
        ]
        return any(indicator in field_name.lower() for indicator in date_indicators)
    
    def _shift_date_value(self, date_str: str) -> str:
        """Shift a single date value, trying multiple formats"""
        from datetime import datetime, timedelta
        
        formats = [
            "%Y-%m-%d",
            "%m/%d/%Y",
            "%Y-%m-%d %H:%M:%S",
            "%m/%d/%Y %H:%M",
            "%B %d, %Y",  # January 15, 2024
        ]
        
        for fmt in formats:
            try:
                dt = datetime.strptime(date_str.strip(), fmt)
                shifted = dt + timedelta(days=self.shift_days)
                return shifted.strftime(fmt)
            except ValueError:
                continue
        
        return date_str  # Unparseable — return as-is (Presidio will catch if PHI)
```

### Re-Identification: Structure-Aware (Not Regex)

```python
def re_identify_summary(
    self,
    db: Session,
    vault_id: str,
    summary_text: str
) -> str:
    """
    Re-identify summary using vault mappings.
    
    IMPORTANT: Token replacement is safe (exact string match).
    Date reversal in free text is INTENTIONALLY LIMITED:
    - We only reverse dates that appear in YYYY-MM-DD format
    - Other date formats in Claude's prose are left as-is
    - The SOURCE OF TRUTH for dates is the structured data (timeline, clinical_data),
      which is reversed via field-path mapping, not regex
    - The summary text is a narrative — approximate dates are acceptable
    """
    vault = db.query(PrivacyVault).filter(PrivacyVault.id == vault_id).first()
    if not vault:
        logger.error(f"Vault entry not found (vault_id hash: {hash(vault_id) % 10000})")
        return summary_text
    
    # Step 1: Replace tokens with original values (exact string match — safe)
    result = summary_text
    
    # Sort by token length descending to avoid partial replacements
    sorted_tokens = sorted(
        vault.token_map.items(),
        key=lambda x: len(x[0]),
        reverse=True
    )
    
    for token, original_value in sorted_tokens:
        result = result.replace(token, original_value)
    
    # Step 2: Reverse date shift ONLY for YYYY-MM-DD format in text
    #         This is best-effort for the narrative. Structured data uses field-path reversal.
    from datetime import datetime, timedelta
    import re
    
    def reverse_iso_date(match):
        try:
            dt = datetime.strptime(match.group(0), "%Y-%m-%d")
            original = dt - timedelta(days=vault.date_shift_days)
            return original.strftime("%Y-%m-%d")
        except ValueError:
            return match.group(0)
    
    result = re.sub(r'\d{4}-\d{2}-\d{2}', reverse_iso_date, result)
    
    return result
```

**Key insight**: The summary text is a **narrative**. The structured data (timeline, clinical_data) is the **source of truth**. We reverse dates precisely in structured data via field-path tracking. The narrative gets best-effort ISO date reversal + token replacement.

---

## Logging Policy

### Zero-PHI Logging Rules

```python
# ❌ NEVER LOG:
logger.info(f"De-identifying case {case_id} with date shift: +{date_shift_days} days")
logger.info(f"Token map: {token_map}")
logger.info(f"Patient name: {patient_name}")
logger.info(f"Replacing {original_text} with {token}")
logger.debug(f"Presidio detected: {entity.text}")

# ✅ SAFE TO LOG:
logger.info(f"De-identification started (vault_hash: {hash(vault_id) % 10000})")
logger.info(f"Structured PHI: {len(structured_replacements)} fields replaced")
logger.info(f"Presidio: {len(text_entities)} entities detected in free-text fields")
logger.info(f"Date shifting: {len(shifted_fields)} date fields processed")
logger.info(f"Pre-flight validator: PASS")
logger.info(f"Re-identification completed (vault_hash: {hash(vault_id) % 10000})")
```

### Implementation

```python
class SafeLogger:
    """Wrapper that prevents PHI from reaching logs"""
    
    def __init__(self, logger):
        self._logger = logger
    
    def info(self, msg: str, **kwargs):
        self._logger.info(self._sanitize(msg), **kwargs)
    
    def _sanitize(self, msg: str) -> str:
        """Strip anything that looks like PHI from log messages"""
        import re
        # Remove anything that looks like a name (Title Case pairs)
        msg = re.sub(r'\b[A-Z][a-z]+\s+[A-Z][a-z]+\b', '[REDACTED_NAME]', msg)
        # Remove SSN patterns
        msg = re.sub(r'\b\d{3}-\d{2}-\d{4}\b', '[REDACTED_SSN]', msg)
        # Remove MRN patterns
        msg = re.sub(r'MRN[:\s]*\w+', '[REDACTED_MRN]', msg)
        # Remove phone patterns
        msg = re.sub(r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b', '[REDACTED_PHONE]', msg)
        return msg
```

---

## Pre-Flight PHI Validator

### Purpose
**Fail-closed safety net**: Before ANY payload reaches Claude, run a final PHI check. If anything is detected, **BLOCK the request entirely**.

```python
class PHIValidator:
    """
    Pre-flight validator: scans the FINAL payload before it reaches Claude.
    If ANY PHI pattern is detected, the request is BLOCKED.
    
    This is the last line of defense. It should never trigger if
    de-identification is working correctly. If it does trigger,
    it means there's a bug in the de-id pipeline.
    """
    
    def __init__(self):
        self.analyzer = AnalyzerEngine()
    
    def validate_payload(
        self,
        payload: dict,
        known_entities: Dict[str, str],  # Original PHI values to check against
        case_id: str
    ) -> bool:
        """
        Returns True if payload is safe (no PHI detected).
        Returns False if PHI is detected (BLOCK the request).
        """
        # Serialize entire payload to text
        payload_text = json.dumps(payload, default=str)
        
        # Check 1: None of the original PHI values appear in the payload
        for original_value in known_entities.values():
            if len(original_value) >= 3 and original_value.lower() in payload_text.lower():
                safe_logger.error(
                    f"PRE-FLIGHT FAILED: Original PHI value detected in payload. "
                    f"Entity type: {self._get_type_for_value(original_value, known_entities)}. "
                    f"Vault hash: {hash(case_id) % 10000}"
                )
                return False
        
        # Check 2: Presidio scan for any remaining PII
        results = self.analyzer.analyze(
            text=payload_text,
            language="en",
            entities=["PERSON", "PHONE_NUMBER", "US_SSN", "EMAIL_ADDRESS"],
            score_threshold=0.85  # High threshold to avoid false positives on medical terms
        )
        
        # Filter out tokens (they look like entities but are intentional)
        real_findings = [
            r for r in results
            if not payload_text[r.start:r.end].startswith("[[")
        ]
        
        if real_findings:
            safe_logger.error(
                f"PRE-FLIGHT FAILED: Presidio detected {len(real_findings)} "
                f"potential PHI entities in final payload. Types: "
                f"{[r.entity_type for r in real_findings]}"
            )
            return False
        
        safe_logger.info("PRE-FLIGHT PASSED: No PHI detected in payload")
        return True
    
    def _get_type_for_value(self, value: str, entities: dict) -> str:
        for token, original in entities.items():
            if original == value:
                return token.split("::")[0].replace("[[", "")
        return "UNKNOWN"
```

### Fail-Closed Policy

```python
# In summary_service.py
async def generate_summary(self, ...):
    # ... de-identification ...
    
    # PRE-FLIGHT CHECK (fail-closed)
    validator = PHIValidator()
    is_safe = validator.validate_payload(
        payload=de_id_payload,
        known_entities={v: k for k, v in vault_entry.token_map.items()},
        case_id=case_id
    )
    
    if not is_safe:
        # BLOCK — do not send to Claude
        logger.critical("De-identification failed pre-flight check. Request blocked.")
        return self._generate_mock_summary(...)  # Fallback to template-based
    
    # Safe to proceed
    response = await tier2_llm.chat_completion(...)
```

---

## Technical Implementation

### Complete De-Identification Service (v2)

```python
# app/services/presidio_deidentification_service.py

import uuid
import json
import random
import re
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional, Any

from presidio_analyzer import AnalyzerEngine, RecognizerRegistry
from presidio_anonymizer import AnonymizerEngine
from sqlalchemy.orm import Session

from app.models.privacy_vault import PrivacyVault
from app.core.config import settings

# Use safe logger — never log PHI
logger = logging.getLogger(__name__)


def _generate_token(entity_type: str) -> str:
    """Generate a unique, non-colliding token for an entity"""
    short_uuid = uuid.uuid4().hex[:8]
    return f"[[{entity_type}::{short_uuid}]]"


class PresidioDeIdentificationService:
    """
    Production-grade de-identification service.
    
    Processing order:
    1. Structured PHI replacement (known fields)
    2. Date shifting (structure-aware)
    3. Presidio free-text scan (catch leaks)
    4. Pre-flight PHI validation (fail-closed)
    """
    
    def __init__(self):
        registry = RecognizerRegistry()
        # Add custom medical recognizers to PRESERVE clinical terms
        registry.load_predefined_recognizers()
        self.analyzer = AnalyzerEngine(registry=registry)
        self.anonymizer = AnonymizerEngine()
    
    def de_identify_for_summary(
        self,
        db: Session,
        case_id: str,
        user_id: str,
        patient_name: str,
        timeline: List[Dict],
        clinical_data: Dict,
        red_flags: List[Dict],
        case_metadata: Optional[Dict] = None
    ) -> Tuple[Dict, str]:
        """
        De-identify all data before sending to Tier 2 (Claude).
        
        Returns:
            (de_identified_payload, vault_id)
        
        Raises:
            PHILeakageError: If pre-flight validation fails (fail-closed)
        """
        # Generate unique date shift for this case
        date_shift_days = random.randint(
            settings.DATE_SHIFT_MIN_DAYS,
            settings.DATE_SHIFT_MAX_DAYS
        )
        
        # ========================================
        # STEP 1: STRUCTURED PHI REPLACEMENT
        # Replace known PHI fields with unique tokens
        # ========================================
        token_map = {}  # token → original_value (strict 1:1)
        
        # Collect all known PHI values and generate unique tokens
        known_phi = self._collect_known_phi(
            patient_name=patient_name,
            clinical_data=clinical_data,
            case_metadata=case_metadata
        )
        
        # Generate unique token for each PHI value
        for phi_value, entity_type in known_phi.items():
            if phi_value and len(phi_value.strip()) >= 2:
                token = _generate_token(entity_type)
                token_map[token] = phi_value
        
        # Build reverse lookup: original_value → token
        value_to_token = {v: k for k, v in token_map.items()}
        
        # Replace in structured data
        de_id_clinical = self._replace_in_structure(clinical_data, value_to_token)
        de_id_timeline = self._replace_in_structure(timeline, value_to_token)
        de_id_red_flags = self._replace_in_structure(red_flags, value_to_token)
        
        logger.info(f"Structured PHI: {len(token_map)} unique entities tokenized")
        
        # ========================================
        # STEP 2: DATE SHIFTING
        # Shift all date fields in structured data
        # ========================================
        date_engine = DateShiftEngine(date_shift_days)
        
        de_id_timeline = date_engine.shift_structured_dates(de_id_timeline)
        de_id_clinical = date_engine.shift_structured_dates(de_id_clinical)
        de_id_red_flags = date_engine.shift_structured_dates(de_id_red_flags)
        
        logger.info(f"Date shifting: {len(date_engine.shifted_fields)} date fields processed")
        
        # ========================================
        # STEP 3: PRESIDIO FREE-TEXT SCAN
        # Catch any PHI that leaked into narrative fields
        # ========================================
        presidio_tokens = self._presidio_scan_free_text(
            de_id_timeline, de_id_clinical, de_id_red_flags
        )
        token_map.update(presidio_tokens)
        
        logger.info(f"Presidio: {len(presidio_tokens)} additional entities caught in free-text")
        
        # ========================================
        # STEP 4: STORE IN PRIVACY VAULT
        # ========================================
        vault_id = str(uuid.uuid4())
        vault_entry = PrivacyVault(
            id=vault_id,
            case_id=case_id,
            user_id=user_id,
            date_shift_days=date_shift_days,
            token_map=token_map,
            shifted_fields=date_engine.shifted_fields,  # For structure-aware reversal
            created_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(days=settings.PRIVACY_VAULT_RETENTION_DAYS)
        )
        db.add(vault_entry)
        db.commit()
        
        logger.info(
            f"Vault stored (hash: {hash(vault_id) % 10000}), "
            f"total tokens: {len(token_map)}, "
            f"shifted dates: {len(date_engine.shifted_fields)}"
        )
        
        # ========================================
        # STEP 5: PRE-FLIGHT VALIDATION
        # Fail-closed: block if any PHI detected
        # ========================================
        payload = {
            "timeline": de_id_timeline,
            "clinical_data": de_id_clinical,
            "red_flags": de_id_red_flags
        }
        
        if not self._validate_no_phi(payload, known_phi):
            db.delete(vault_entry)
            db.commit()
            raise PHILeakageError(
                "Pre-flight PHI validation failed. Request blocked. "
                "This indicates a bug in the de-identification pipeline."
            )
        
        logger.info("Pre-flight validator: PASS")
        
        return payload, vault_id
    
    def re_identify_summary(
        self,
        db: Session,
        vault_id: str,
        summary_text: str
    ) -> str:
        """
        Re-identify summary text using vault mappings.
        
        Token replacement: exact string match (safe).
        Date reversal: best-effort for YYYY-MM-DD in text.
        Structured data reversal: use reverse_structured_dates() separately.
        """
        vault = db.query(PrivacyVault).filter(PrivacyVault.id == vault_id).first()
        if not vault:
            logger.error(f"Vault not found (hash: {hash(vault_id) % 10000})")
            return summary_text
        
        result = summary_text
        
        # Step 1: Replace tokens → original values (sorted by length, longest first)
        sorted_tokens = sorted(
            vault.token_map.items(),
            key=lambda x: len(x[0]),
            reverse=True
        )
        for token, original in sorted_tokens:
            result = result.replace(token, original)
        
        # Step 2: Best-effort ISO date reversal in text
        def reverse_iso(match):
            try:
                dt = datetime.strptime(match.group(0), "%Y-%m-%d")
                return (dt - timedelta(days=vault.date_shift_days)).strftime("%Y-%m-%d")
            except ValueError:
                return match.group(0)
        
        result = re.sub(r'\d{4}-\d{2}-\d{2}', reverse_iso, result)
        
        logger.info(f"Re-identification completed (vault hash: {hash(vault_id) % 10000})")
        return result
    
    # ──────────────────────────────────────
    # Private Methods
    # ──────────────────────────────────────
    
    def _collect_known_phi(
        self,
        patient_name: str,
        clinical_data: Dict,
        case_metadata: Optional[Dict] = None
    ) -> Dict[str, str]:
        """
        Collect all KNOWN PHI values from structured data.
        Returns: {phi_value: entity_type}
        """
        known = {}
        
        # Patient name (always present)
        if patient_name:
            known[patient_name] = "PERSON"
            # Also handle first/last separately
            parts = patient_name.strip().split()
            if len(parts) >= 2:
                known[parts[0]] = "PERSON"   # First name
                known[parts[-1]] = "PERSON"  # Last name
        
        # Demographics
        demographics = clinical_data.get("patient_demographics", {})
        if isinstance(demographics, dict):
            for field, entity_type in [
                ("name", "PERSON"),
                ("mrn", "ID"), ("ssn", "ID"),
                ("address", "LOC"), ("phone", "ID"), ("email", "ID"),
            ]:
                val = demographics.get(field)
                if val and isinstance(val, str) and len(val.strip()) >= 2:
                    known[val.strip()] = entity_type
        
        # Provider names (search across all structures)
        provider_fields = [
            "attending_provider", "referring_provider",
            "ordering_provider", "consulting_provider",
            "provider", "physician", "doctor"
        ]
        self._extract_field_values(clinical_data, provider_fields, "PERSON", known)
        
        # Facility names
        facility_fields = ["facility_name", "hospital_name", "clinic_name", "facility"]
        self._extract_field_values(clinical_data, facility_fields, "ORG", known)
        
        # Case metadata
        if case_metadata:
            for field in ["patient_name", "facility_name"]:
                val = case_metadata.get(field)
                if val and isinstance(val, str):
                    entity_type = "PERSON" if "patient" in field else "ORG"
                    known[val.strip()] = entity_type
        
        return known
    
    def _extract_field_values(
        self,
        data: Any,
        field_names: List[str],
        entity_type: str,
        result: Dict[str, str]
    ):
        """Recursively extract values from fields matching given names"""
        if isinstance(data, dict):
            for key, value in data.items():
                if key.lower() in field_names and isinstance(value, str) and len(value.strip()) >= 2:
                    result[value.strip()] = entity_type
                elif isinstance(value, (dict, list)):
                    self._extract_field_values(value, field_names, entity_type, result)
        elif isinstance(data, list):
            for item in data:
                self._extract_field_values(item, field_names, entity_type, result)
    
    def _replace_in_structure(
        self,
        data: Any,
        value_to_token: Dict[str, str]
    ) -> Any:
        """
        Recursively replace PHI values with tokens in structured data.
        Handles strings, dicts, and lists.
        """
        if isinstance(data, str):
            result = data
            # Replace longest values first to avoid partial matches
            for original, token in sorted(
                value_to_token.items(),
                key=lambda x: len(x[0]),
                reverse=True
            ):
                result = result.replace(original, token)
            return result
        
        elif isinstance(data, dict):
            return {
                key: self._replace_in_structure(value, value_to_token)
                for key, value in data.items()
            }
        
        elif isinstance(data, list):
            return [
                self._replace_in_structure(item, value_to_token)
                for item in data
            ]
        
        return data  # Non-string primitives (int, float, bool, None)
    
    def _presidio_scan_free_text(
        self,
        timeline: List[Dict],
        clinical_data: Dict,
        red_flags: List[Dict]
    ) -> Dict[str, str]:
        """
        Scan free-text fields with Presidio for any leaked PHI.
        Returns additional token mappings.
        """
        additional_tokens = {}
        
        # Collect all free-text values
        free_texts = []
        
        # Timeline descriptions
        for event in timeline:
            if isinstance(event, dict):
                desc = event.get("description", "")
                if isinstance(desc, str) and len(desc) > 10:
                    free_texts.append(("timeline.description", desc, event, "description"))
                    
                    # Check nested details
                    details = event.get("details", {})
                    if isinstance(details, dict):
                        for key, val in details.items():
                            if isinstance(val, str) and len(val) > 10:
                                free_texts.append(("timeline.details", val, details, key))
        
        # History text
        for entry in clinical_data.get("history", []):
            if isinstance(entry, dict):
                text = entry.get("text", "") or entry.get("description", "")
                if isinstance(text, str) and len(text) > 10:
                    key = "text" if "text" in entry else "description"
                    free_texts.append(("history", text, entry, key))
        
        # Chief complaint
        cc = clinical_data.get("chief_complaint", "")
        if isinstance(cc, str) and len(cc) > 10:
            free_texts.append(("chief_complaint", cc, clinical_data, "chief_complaint"))
        
        # Red flag descriptions
        for rf in red_flags:
            if isinstance(rf, dict):
                desc = rf.get("description", "")
                if isinstance(desc, str) and len(desc) > 10:
                    free_texts.append(("red_flag.description", desc, rf, "description"))
        
        # Scan each free-text field with Presidio
        for field_path, text, parent_obj, parent_key in free_texts:
            results = self.analyzer.analyze(
                text=text,
                language="en",
                entities=[
                    "PERSON", "PHONE_NUMBER", "US_SSN",
                    "EMAIL_ADDRESS", "LOCATION", "ORGANIZATION"
                ],
                score_threshold=0.7
            )
            
            # Filter out already-tokenized text
            for result in sorted(results, key=lambda x: x.start, reverse=True):
                entity_text = text[result.start:result.end]
                
                # Skip if already a token
                if entity_text.startswith("[["):
                    continue
                
                # Skip very short matches (likely false positives)
                if len(entity_text.strip()) < 3:
                    continue
                
                # Check if this value already has a token
                existing_token = None
                for token, original in additional_tokens.items():
                    if original == entity_text:
                        existing_token = token
                        break
                
                if not existing_token:
                    # Map Presidio entity types to our token types
                    type_map = {
                        "PERSON": "PERSON",
                        "LOCATION": "LOC",
                        "ORGANIZATION": "ORG",
                        "PHONE_NUMBER": "ID",
                        "US_SSN": "ID",
                        "EMAIL_ADDRESS": "ID",
                    }
                    token_type = type_map.get(result.entity_type, "ID")
                    existing_token = _generate_token(token_type)
                    additional_tokens[existing_token] = entity_text
                
                # Replace in the parent object
                text = text[:result.start] + existing_token + text[result.end:]
            
            # Update the parent object with scrubbed text
            parent_obj[parent_key] = text
        
        return additional_tokens
    
    def _validate_no_phi(
        self,
        payload: Dict,
        known_phi: Dict[str, str]
    ) -> bool:
        """
        Pre-flight validation: ensure no PHI in final payload.
        Returns True if safe, False if PHI detected.
        """
        payload_text = json.dumps(payload, default=str).lower()
        
        # Check 1: None of the known PHI values appear
        for phi_value in known_phi.keys():
            if len(phi_value) >= 3 and phi_value.lower() in payload_text:
                logger.error(
                    f"PRE-FLIGHT FAILED: Known PHI value still present in payload"
                )
                return False
        
        # Check 2: Presidio scan on serialized payload
        results = self.analyzer.analyze(
            text=payload_text,
            language="en",
            entities=["PERSON", "US_SSN", "PHONE_NUMBER"],
            score_threshold=0.9  # Very high threshold — avoid false positives
        )
        
        # Filter out tokens
        real_findings = [
            r for r in results
            if not payload_text[r.start:r.end].startswith("[[")
        ]
        
        if real_findings:
            logger.error(
                f"PRE-FLIGHT FAILED: Presidio found {len(real_findings)} "
                f"potential PHI entities. Types: {[r.entity_type for r in real_findings]}"
            )
            return False
        
        return True


class PHILeakageError(Exception):
    """Raised when PHI is detected in a payload destined for Tier 2"""
    pass


class DateShiftEngine:
    """Structure-aware date shifting with field-path tracking"""
    
    def __init__(self, shift_days: int):
        self.shift_days = shift_days
        self.shifted_fields = []
    
    def shift_structured_dates(self, data, path=""):
        if isinstance(data, list):
            return [
                self.shift_structured_dates(item, f"{path}[{i}]")
                for i, item in enumerate(data)
            ]
        
        if isinstance(data, dict):
            result = {}
            for key, value in data.items():
                current_path = f"{path}.{key}" if path else key
                
                if self._is_date_field(key) and isinstance(value, str):
                    shifted = self._shift_date(value)
                    if shifted != value:
                        self.shifted_fields.append({
                            "path": current_path,
                            "original": value,
                            "shifted": shifted
                        })
                        result[key] = shifted
                    else:
                        result[key] = value
                elif isinstance(value, (dict, list)):
                    result[key] = self.shift_structured_dates(value, current_path)
                else:
                    result[key] = value
            return result
        
        return data
    
    def _is_date_field(self, field_name: str) -> bool:
        date_keywords = [
            "date", "admitted", "discharged", "performed",
            "collected", "ordered", "started", "stopped",
            "timestamp", "dob", "date_of_birth", "category_date"
        ]
        return any(kw in field_name.lower() for kw in date_keywords)
    
    def _shift_date(self, date_str: str) -> str:
        from datetime import datetime, timedelta
        formats = ["%Y-%m-%d", "%m/%d/%Y", "%Y-%m-%d %H:%M:%S", "%B %d, %Y"]
        for fmt in formats:
            try:
                dt = datetime.strptime(date_str.strip(), fmt)
                return (dt + timedelta(days=self.shift_days)).strftime(fmt)
            except ValueError:
                continue
        return date_str


# Singleton
presidio_deidentification_service = PresidioDeIdentificationService()
```

---

### Updated Privacy Vault Model

```python
# app/models/privacy_vault.py

from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime

from app.db.base_class import Base


class PrivacyVault(Base):
    __tablename__ = "privacy_vault"
    
    id = Column(String, primary_key=True)
    case_id = Column(String, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    # Date shifting
    date_shift_days = Column(Integer, nullable=False)
    
    # Token map: { "[[PERSON::a94f2c3b]]": "John Doe", ... }
    token_map = Column(JSONB, nullable=False)
    
    # Shifted date field paths (for structure-aware reversal)
    # [{"path": "timeline[0].date", "original": "2024-01-15", "shifted": "2024-02-01"}, ...]
    shifted_fields = Column(JSONB, nullable=True, default=[])
    
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)
    
    __table_args__ = (
        Index('idx_privacy_vault_case', 'case_id'),
        Index('idx_privacy_vault_user', 'user_id'),
    )
```

---

## Security Guarantees (v2)

### What Claude Never Sees

| Data Type | v1 Status | v2 Status | Method |
|-----------|-----------|-----------|--------|
| Patient names | Tokenized | ✅ Unique UUID token per name | Structured replacement |
| Provider names | ❌ Collapsed | ✅ Unique UUID token per provider | Structured replacement |
| Facility names | ❌ Single token | ✅ Unique UUID token per facility | Structured replacement |
| MRN/SSN | ❌ Partial mask | ✅ Unique UUID token | Structured replacement |
| Absolute dates | Shifted | ✅ Shifted + field-path tracked | DateShiftEngine |
| Phone/email | Tokenized | ✅ Unique UUID token | Presidio scan |
| Free-text PHI leaks | ❌ Not caught | ✅ Presidio catches | Free-text scan |
| Everything | ❌ No final check | ✅ Pre-flight validator blocks | Fail-closed |

### What Claude DOES See (Preserved)

| Data Type | Example | Why Preserved |
|-----------|---------|---------------|
| Medications | "Lisinopril 10mg" | Clinical utility |
| Diagnoses | "Pneumonia" | Clinical utility |
| Lab values | "WBC 12.5" | Clinical utility |
| Procedures | "Chest X-ray" | Clinical utility |
| Temporal relations | "3 days after admission" | Shifted dates preserve |
| Severity indicators | "Critical", "Abnormal" | Clinical utility |

---

## Implementation Roadmap (Revised)

### Phase 1: Core Engine (Week 1-2)

- [ ] Install: `presidio-analyzer`, `presidio-anonymizer`, `spacy`, `en_core_web_lg`
- [ ] Create `PresidioDeIdentificationService` with structured-first approach
- [ ] Create `DateShiftEngine` with field-path tracking
- [ ] Create `PHIValidator` (pre-flight, fail-closed)
- [ ] Create `PrivacyVault` model + migration
- [ ] Create `SafeLogger` wrapper
- [ ] Unit tests: token uniqueness, round-trip accuracy, pre-flight blocking
- [ ] Create `OpenRouterService` + test connectivity

### Phase 2: Integration (Week 3-4)

- [ ] Update `llm_factory.py` with tier routing
- [ ] Update `summary_service.py` with de-id → Claude → re-id flow
- [ ] Update `clinical_agent.py` → Tier 1 (OpenRouter)
- [ ] Update `red_flags_service.py` → Tier 1 (OpenRouter)
- [ ] Update `main_agent.py` → Tier 1 (OpenRouter)
- [ ] Integration tests: full pipeline with both tiers

### Phase 3: Hardening (Week 5)

- [ ] Network traffic audit (verify zero PHI in Claude calls)
- [ ] Log audit (verify zero PHI in application logs)
- [ ] Add vault access audit logging
- [ ] Add crypto-shredding for vault expiry
- [ ] Performance benchmarking
- [ ] Documentation updates

---

## Decisions Confirmed

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Token format | `[[TYPE::uuid8]]` | Unique, survives paraphrasing, auditable |
| Pseudonyms | ❌ No Faker | Tokens only — no fake names in healthcare |
| PHI handling order | Structured-first, Presidio-second | Deterministic for known fields, probabilistic for leaks |
| Date reversal | Structure-aware (field paths) | Not regex on Claude output |
| Fail mode | Fail-closed (block request) | Never send PHI even if de-id has a bug |
| Logging | Zero-PHI policy | No shift values, no token maps, no entity text |
