
"""Presidio Lab API — Advanced PHI de-identification testing endpoints.

These endpoints power the internal Presidio Lab UI for testing and tuning
the same de-identification pipeline used by Tier 2 (Claude) processing.
"""

import re
from collections import Counter
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.db.session import get_db
from app.api.endpoints.auth import get_current_user
from app.services.presidio_deidentification_service import presidio_deidentification_service
from app.services.date_shift_service import shift_dates_in_text, DATE_PATTERNS
from app.utils.date_utils import normalize_date_format
from app.models.privacy_vault import PrivacyVault
from app.utils.safe_logger import get_safe_logger

router = APIRouter()
safe_logger = get_safe_logger(__name__)

# All entity types supported by Presidio
ALL_ENTITY_TYPES = [
    "PERSON", "DATE_TIME", "PHONE_NUMBER", "US_SSN", "EMAIL_ADDRESS",
    "LOCATION", "ORGANIZATION", "NRP", "CREDIT_CARD", "CRYPTO",
    "IP_ADDRESS", "MEDICAL_LICENSE", "URL", "IBAN_CODE", "US_DRIVER_LICENSE",
    "US_PASSPORT", "US_BANK_NUMBER", "US_ITIN", "AU_ABN", "AU_ACN",
    "AU_TFN", "AU_MEDICARE", "SG_NRIC_FIN", "UK_NHS", "IN_PAN",
    "IN_AADHAAR", "IN_VEHICLE_REGISTRATION",
    "MRN", "TIME", "HOSPITAL", "PROVIDER", "PATIENT_FULL_NAME", "CITY", "AGE", "ID",
    "STREET_ADDRESS", "ZIP_CODE", "NPI", "INSURANCE_ID",
]

# Default entities for medical context
DEFAULT_MEDICAL_ENTITIES = [
    "PERSON", "DATE_TIME", "PHONE_NUMBER", "US_SSN", "EMAIL_ADDRESS",
    "LOCATION", "ORGANIZATION", "MRN", "TIME", "HOSPITAL", "PROVIDER", "PATIENT_FULL_NAME", "CITY",
    "STREET_ADDRESS", "ZIP_CODE", "NPI", "INSURANCE_ID",
]


# ─── Request / Response Models ───────────────────────────────────────────────

class AdvancedAnalyzeRequest(BaseModel):
    text: str = Field(..., description="Text to analyze for PHI")
    score_threshold: float = Field(0.35, ge=0.0, le=1.0, description="Minimum confidence score to report an entity")
    entities: Optional[List[str]] = Field(None, description="Entity types to detect (default: medical set)")
    de_id_approach: str = Field("replace", description="Anonymization approach: replace, redact, hash, mask")
    date_shift_days: int = Field(0, ge=-3650, le=3650, description="Days to shift detected dates (0 = no shift)")
    allowlist: Optional[List[str]] = Field(None, description="Words to NOT flag as PHI")
    denylist: Optional[List[str]] = Field(None, description="Words to force-flag as PHI")
    add_explanations: bool = Field(False, description="Include Presidio analysis explanations")


class EntityResult(BaseModel):
    index: int
    entity_type: str
    text: str
    start: int
    end: int
    score: float
    explanation: Optional[str] = None


class DateShiftResult(BaseModel):
    original: str
    shifted: str
    start: int
    end: int


class AdvancedAnalyzeResponse(BaseModel):
    entities: List[EntityResult]
    de_identified_text: str
    original_text: str
    original_text_length: int
    date_shifts: List[DateShiftResult]
    stats: Dict[str, int]
    engine_info: Dict[str, Any]
    settings_used: Dict[str, Any]


# ─── Endpoints ───────────────────────────────────────────────────────────────

@router.post("/analyze", response_model=AdvancedAnalyzeResponse)
def analyze_text_advanced(request: AdvancedAnalyzeRequest):
    """
    Advanced analysis endpoint with full control over Presidio behavior.
    This uses the EXACT SAME analyzer engine that powers Tier 2 de-identification.
    """
    text = request.text
    if not text:
        return AdvancedAnalyzeResponse(
            entities=[], de_identified_text="", original_text="",
            original_text_length=0, date_shifts=[], stats={},
            engine_info=presidio_deidentification_service.get_engine_info(),
            settings_used={},
        )

    try:
        if not presidio_deidentification_service.analyzer:
            raise HTTPException(status_code=503, detail="Presidio analyzer not initialized")

        # Determine entities to scan for
        entities_to_detect = request.entities or DEFAULT_MEDICAL_ENTITIES
        # Validate entity types
        entities_to_detect = [e for e in entities_to_detect if e in ALL_ENTITY_TYPES]

        # Build allow_list from user input
        allow_list = request.allowlist or []

        # ── Step 1: Run Presidio analysis ──
        results = presidio_deidentification_service.analyzer.analyze(
            text=text,
            entities=entities_to_detect,
            language="en",
            score_threshold=request.score_threshold,
            allow_list=allow_list,
        )

        # Sort results by start position
        results.sort(key=lambda r: r.start)

        # ── Step 2: Handle denylist (force additional detections) ──
        denylist_results = []
        if request.denylist:
            for deny_word in request.denylist:
                if not deny_word.strip():
                    continue
                # Find all occurrences of deny word in text (case-insensitive)
                pattern = re.compile(re.escape(deny_word), re.IGNORECASE)
                for match in pattern.finditer(text):
                    # Check if this span is already covered by existing results
                    already_covered = any(
                        r.start <= match.start() and r.end >= match.end()
                        for r in results
                    )
                    if not already_covered:
                        denylist_results.append({
                            "entity_type": "CUSTOM_PII",
                            "text": text[match.start():match.end()],
                            "start": match.start(),
                            "end": match.end(),
                            "score": 1.0,
                            "explanation": f"Denylist match: '{deny_word}'",
                        })

        # ── Step 3: Format entity results ──
        entity_results = []
        for i, res in enumerate(results):
            explanation_str = None
            if request.add_explanations and res.analysis_explanation:
                explanation_str = str(res.analysis_explanation)

            entity_results.append(EntityResult(
                index=i + 1,
                entity_type=res.entity_type,
                text=text[res.start:res.end],
                start=res.start,
                end=res.end,
                score=round(res.score, 4),
                explanation=explanation_str,
            ))

        # Add denylist results
        for j, dr in enumerate(denylist_results):
            entity_results.append(EntityResult(
                index=len(entity_results) + 1,
                entity_type=dr["entity_type"],
                text=dr["text"],
                start=dr["start"],
                end=dr["end"],
                score=dr["score"],
                explanation=dr["explanation"],
            ))

        # Re-sort by start position for consistent display
        entity_results.sort(key=lambda e: e.start)
        # Re-index
        for idx, er in enumerate(entity_results):
            er.index = idx + 1

        # ── Step 4: De-identify text based on approach ──
        from presidio_anonymizer.entities import OperatorConfig

        approach = request.de_id_approach.lower()

        if approach == "redact":
            operators = {"DEFAULT": OperatorConfig("redact")}
        elif approach == "hash":
            operators = {"DEFAULT": OperatorConfig("hash", {"hash_type": "sha256"})}
        elif approach == "mask":
            operators = {"DEFAULT": OperatorConfig("mask", {"masking_char": "*", "chars_to_mask": 100, "from_end": False})}
        else:
            # Default: replace with <ENTITY_TYPE>
            operators = {"DEFAULT": OperatorConfig("replace")}

        # Combine Presidio results with denylist for anonymization
        all_analyzer_results = list(results)

        # For denylist items, create mock analyzer results for the anonymizer
        if denylist_results:
            from presidio_analyzer import RecognizerResult
            for dr in denylist_results:
                all_analyzer_results.append(
                    RecognizerResult(
                        entity_type=dr["entity_type"],
                        start=dr["start"],
                        end=dr["end"],
                        score=dr["score"],
                    )
                )

        # ── SPECIAL HANDLING: Date Shifting vs Redaction ──
        # If date shifting is enabled (days != 0), we want to SHIFT dates, not redact them.
        # So we filter out DATE_TIME entities from the anonymizer list.
        # They will be handled in Step 5 by the regex-based shifter.
        if request.date_shift_days != 0:
            all_analyzer_results = [
                r for r in all_analyzer_results 
                if r.entity_type != "DATE_TIME"
            ]

        anonymized = presidio_deidentification_service.anonymizer.anonymize(
            text=text,
            analyzer_results=all_analyzer_results,
            operators=operators,
        )
        de_identified_text = anonymized.text

        # ── Step 5: Date shifting ──
        date_shifts = []
        if request.date_shift_days != 0:
            # Find all dates in the de-identified text BEFORE shifting
            # We shift the de-identified output so dates in replaced tokens won't double-shift
            pre_shift_text = de_identified_text

            # Find all dates in ORIGINAL text for reporting
            for pattern, _ in DATE_PATTERNS:
                for m in pattern.finditer(text):
                    original_date = text[m.start():m.end()]
                    normalized = normalize_date_format(original_date)
                    if normalized:
                        from app.services.date_shift_service import _shift_date_str
                        shifted = _shift_date_str(normalized, request.date_shift_days, 1)
                        date_shifts.append(DateShiftResult(
                            original=original_date,
                            shifted=shifted,
                            start=m.start(),
                            end=m.end(),
                        ))

            # Apply date shifting to de-identified text
            de_identified_text = shift_dates_in_text(
                de_identified_text, request.date_shift_days, direction=1
            )

        # ── Step 6: Stats ──
        type_counter = Counter(e.entity_type for e in entity_results)
        stats = dict(type_counter)
        stats["total"] = len(entity_results)

        return AdvancedAnalyzeResponse(
            entities=entity_results,
            de_identified_text=de_identified_text,
            original_text=text,
            original_text_length=len(text),
            date_shifts=date_shifts,
            stats=stats,
            engine_info=presidio_deidentification_service.get_engine_info(),
            settings_used={
                "score_threshold": request.score_threshold,
                "entities": entities_to_detect,
                "de_id_approach": request.de_id_approach,
                "date_shift_days": request.date_shift_days,
                "allowlist": request.allowlist or [],
                "denylist": request.denylist or [],
                "add_explanations": request.add_explanations,
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        safe_logger.error(f"Error in advanced analyze: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ─── Pipeline Preview: Full Tier 2 De-identification ────────────────────────

class PipelinePreviewRequest(BaseModel):
    """Run the full Tier 2 de-identification pipeline on sample data."""
    patient_name: str = Field("John Doe", description="Patient name for PHI replacement")
    case_number: str = Field("CASE-001", description="Case number")
    clinical_data: Dict[str, Any] = Field(default_factory=dict, description="Structured clinical data")
    timeline: List[Dict[str, Any]] = Field(default_factory=list, description="Timeline events")
    red_flags: List[Dict[str, Any]] = Field(default_factory=list, description="Red flags / contradictions")
    date_shift_days: Optional[int] = Field(None, description="Override shift days (random if None)")
    score_threshold: float = Field(0.35, ge=0.0, le=1.0, description="Minimum confidence score for PHI detection")


@router.post("/pipeline-preview")
def pipeline_preview(
    request: PipelinePreviewRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Run the full Tier 2 de-identification pipeline on sample data.
    Shows exactly what Claude would receive — token map, date shifts, final payload.
    Does NOT persist to vault (dry-run mode).
    """
    import random
    from copy import deepcopy
    from app.core.config import settings

    try:
        if not presidio_deidentification_service.analyzer:
            raise HTTPException(status_code=503, detail="Presidio service not available")

        # Determine shift days
        shift_days = request.date_shift_days
        if shift_days is None:
            shift_days = random.randint(
                getattr(settings, "DATE_SHIFT_MIN_DAYS", 0),
                getattr(settings, "DATE_SHIFT_MAX_DAYS", 30),
            )

        # Collect known PHI (same logic as production)
        known_phi = presidio_deidentification_service._collect_known_phi(
            request.patient_name,
            {"case_number": request.case_number},
        )

        # Generate tokens
        token_map = presidio_deidentification_service._generate_tokens(known_phi)

        # Replace known PHI
        de_id_clinical = presidio_deidentification_service._replace_known_phi(
            deepcopy(request.clinical_data), token_map
        )
        de_id_timeline = presidio_deidentification_service._replace_known_phi(
            deepcopy(request.timeline), token_map
        )
        de_id_red_flags = presidio_deidentification_service._replace_known_phi(
            deepcopy(request.red_flags), token_map
        )

        # Shift dates
        shifted_fields = []
        de_id_clinical, clinical_shifts = presidio_deidentification_service._shift_dates_structured(
            de_id_clinical, shift_days, path="clinical_data"
        )
        de_id_timeline, timeline_shifts = presidio_deidentification_service._shift_dates_structured(
            de_id_timeline, shift_days, path="timeline"
        )
        de_id_red_flags, red_flags_shifts = presidio_deidentification_service._shift_dates_structured(
            de_id_red_flags, shift_days, path="red_flags"
        )
        shifted_fields.extend(clinical_shifts + timeline_shifts + red_flags_shifts)

        # Presidio scan free-text fields
        # Respect the threshold provided in the request
        de_id_clinical = presidio_deidentification_service._presidio_scan_free_text(
            de_id_clinical, token_map, score_threshold=request.score_threshold
        )
        de_id_timeline = presidio_deidentification_service._presidio_scan_free_text(
            de_id_timeline, token_map, score_threshold=request.score_threshold
        )
        de_id_red_flags = presidio_deidentification_service._presidio_scan_free_text(
            de_id_red_flags, token_map, score_threshold=request.score_threshold
        )

        # Build response payload
        de_id_payload = {
            "clinical_data": de_id_clinical,
            "timeline": de_id_timeline,
            "red_flags": de_id_red_flags,
        }

        # Format token map for display (reverse: original → token)
        display_token_map = []
        for token, original in token_map.items():
            entity_type = "UNKNOWN"
            if "::" in token:
                parts = token.replace("[[", "").replace("]]", "").split("::")
                if len(parts) >= 1:
                    entity_type = parts[0]
            display_token_map.append({
                "original": original,
                "token": token,
                "type": entity_type,
            })

        return {
            "de_identified_payload": de_id_payload,
            "token_map": display_token_map,
            "date_shift_days": shift_days,
            "shifted_fields": shifted_fields,
            "known_phi_count": len(known_phi),
            "engine_info": presidio_deidentification_service.get_engine_info(),
            "note": "DRY RUN — nothing saved to vault",
        }

    except HTTPException:
        raise
    except Exception as e:
        safe_logger.error(f"Pipeline preview failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ─── Vault Inspector ────────────────────────────────────────────────────────

@router.get("/vault/{case_id}")
def get_case_redactions(
    case_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Retrieve the stored redaction map (Privacy Vault) for a specific case.
    Shows exactly what was redacted and stored during processing.
    """
    vault_entry = db.query(PrivacyVault).filter(
        PrivacyVault.case_id == case_id
    ).order_by(PrivacyVault.created_at.desc()).first()

    if not vault_entry:
        raise HTTPException(status_code=404, detail="No redaction history found for this case")

    mapping = []
    if vault_entry.token_map:
        for token, original in vault_entry.token_map.items():
            entity_type = "UNKNOWN"
            if "::" in token:
                parts = token.replace("[[", "").replace("]]", "").split("::")
                if len(parts) >= 1:
                    entity_type = parts[0]
            mapping.append({
                "original": original,
                "token": token,
                "type": entity_type,
            })

    return {
        "case_id": case_id,
        "vault_id": vault_entry.id,
        "date_shift_days": vault_entry.date_shift_days,
        "created_at": vault_entry.created_at,
        "mappings": mapping,
        "total_redactions": len(mapping),
        "shifted_fields": vault_entry.shifted_fields or [],
    }


# ─── Engine Management ──────────────────────────────────────────────────────

@router.get("/engine-info")
def get_engine_info():
    """Returns the current NER engine info and available models."""
    return presidio_deidentification_service.get_engine_info()


class SwitchEngineRequest(BaseModel):
    engine: Optional[str] = Field(None, description="Engine type (legacy, e.g., 'spacy')")
    model_id: Optional[str] = Field(None, description="Specific model ID from database")


@router.post("/switch-engine")
def switch_engine(
    request: SwitchEngineRequest,
    current_user=Depends(get_current_user),
):
    """Switch the NER engine at runtime. Requires authentication."""
    result = presidio_deidentification_service.switch_ner_engine(
        engine_type=request.engine,
        model_id=request.model_id
    )
    if result.get("status") != "success":
        raise HTTPException(status_code=400, detail=result.get("message", "Failed to switch engine"))
    return result


@router.get("/supported-entities")
def get_supported_entities():
    """Return all supported entity types for the entity picker."""
    return {
        "all_entities": ALL_ENTITY_TYPES,
        "default_medical_entities": DEFAULT_MEDICAL_ENTITIES,
        "entity_descriptions": {
            "PERSON": "Names of individuals",
            "DATE_TIME": "Dates, timestamps, ages",
            "PHONE_NUMBER": "Phone / fax numbers",
            "US_SSN": "US Social Security Numbers",
            "EMAIL_ADDRESS": "Email addresses",
            "LOCATION": "Physical addresses, cities, states",
            "ORGANIZATION": "Hospital names, companies",
            "NRP": "Nationalities, religious groups",
            "CREDIT_CARD": "Credit card numbers",
            "CRYPTO": "Cryptocurrency wallet addresses",
            "IP_ADDRESS": "IP addresses",
            "MEDICAL_LICENSE": "Medical license numbers",
            "URL": "Web URLs",
            "IBAN_CODE": "International bank account numbers",
            "US_DRIVER_LICENSE": "US driver license numbers",
            "US_PASSPORT": "US passport numbers",
            "US_BANK_NUMBER": "US bank account numbers",
            "US_ITIN": "US Individual Taxpayer ID",
            "AU_ABN": "Australian Business Number",
            "AU_ACN": "Australian Company Number",
            "AU_TFN": "Australian Tax File Number",
            "AU_MEDICARE": "Australian Medicare number",
            "SG_NRIC_FIN": "Singapore National ID",
            "UK_NHS": "UK National Health Service number",
            "IN_PAN": "Indian Permanent Account Number",
            "IN_AADHAAR": "Indian Aadhaar number",
            "IN_VEHICLE_REGISTRATION": "Indian vehicle registration",
        },
    }
