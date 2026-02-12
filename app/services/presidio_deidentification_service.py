"""Presidio-based de-identification service for HIPAA-compliant Tier 2 processing.

This service implements the v2.0 architecture with:
1. Structured-first PHI replacement (deterministic tokenization of known fields)
2. UUID12-based tokens ([[TYPE::uuid12]]) with strict 1:1 mapping  
3. Free-text Presidio scan (catches leaks in narrative fields)
4. Structure-aware date shifting with field-path tracking
5. Pre-flight PHI validation (fail-closed safety net)

Key Principle:
> Known PHI is handled deterministically; Presidio is only a leak catcher.

Usage:
    from app.services.presidio_deidentification_service import presidio_deidentification_service
    
    # De-identify before Tier 2
    de_id_payload, vault_id = presidio_deidentification_service.de_identify_for_summary(
        db=db, case_id=case_id, patient_name="John Doe", clinical_data={...}
    )
    
    # Send to Claude with de-identified data
    summary = await claude_service.generate_summary(de_id_payload)
    
    # Re-identify the response
    final_summary = presidio_deidentification_service.re_identify_summary(
        db=db, vault_id=vault_id, summary_text=summary
    )
"""

import json
import random
import re
import uuid
from copy import deepcopy
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.privacy_vault import PrivacyVault
from app.services.phi_validator import phi_validator, PHILeakageError
from app.utils.safe_logger import get_safe_logger

safe_logger = get_safe_logger(__name__)

try:
    from presidio_analyzer import AnalyzerEngine
    from presidio_anonymizer import AnonymizerEngine
    from presidio_analyzer.nlp_engine import NlpEngineProvider

    PRESIDIO_AVAILABLE = True
except ImportError:
    PRESIDIO_AVAILABLE = False
    safe_logger.warning("Presidio not available - de-identification disabled")

# obi/deid_roberta_i2b2 label -> Presidio entity mapping
# The model predicts i2b2 PHI categories; we map them to Presidio types
ROBERTA_LABEL_TO_PRESIDIO = {
    "PATIENT": "PERSON",
    "STAFF": "PERSON",
    "AGE": "AGE",
    "DATE": "DATE_TIME",
    "PHONE": "PHONE_NUMBER",
    "EMAIL": "EMAIL_ADDRESS",
    "ID": "ID",
    "HOSP": "ORGANIZATION",
    "PATORG": "ORGANIZATION",
    "LOC": "LOCATION",
    "OTHERPHI": "NRP",
}

# Model registry: available NER engines
NER_MODEL_REGISTRY = {
    "spacy": {
        "label": "spaCy (en_core_web_lg)",
        "description": "General-purpose NER, fast, good baseline",
        "engine": "spacy",
        "model": "en_core_web_lg",
    },
    "transformers": {
        "label": "RoBERTa Medical (obi/deid_roberta_i2b2)",
        "description": "Medical de-identification model trained on i2b2 clinical data. Best for clinical PHI.",
        "engine": "transformers",
        "model": "obi/deid_roberta_i2b2",
    },
}

# Known PHI field names (used for structured-first replacement)
KNOWN_PHI_FIELDS = {
    "patient_name",
    "patient_first_name",
    "patient_last_name",
    "mrn",
    "medical_record_number",
    "case_number",
    "facility",
    "facility_name",
    "hospital",
    "provider",
    "provider_name",
    "physician",
    "doctor",
    "referring_physician",
}

# Fields that contain free text (requires Presidio scanning)
FREE_TEXT_FIELDS = {
    "description",
    "narrative",
    "note",
    "comment",
    "details",
    "content",
    "text",
    "summary",
}

# Date field keywords (for structure-aware shifting)
DATE_FIELD_KEYWORDS = {
    "date",
    "time",
    "timestamp",
    "occurred",
    "started",
    "ended",
    "admitted",
    "discharged",
}


class PresidioDeIdentificationService:
    """Main de-identification service for Tier 2 (Claude) processing"""

    def __init__(self):
        self.analyzer = None
        self.anonymizer = None
        self.active_ner_engine: str = "spacy"
        self.active_model_name: str = "en_core_web_lg"

        if PRESIDIO_AVAILABLE:
            try:
                self.anonymizer = AnonymizerEngine()
                # Initialize with configured engine
                engine_type = getattr(settings, "PRESIDIO_NER_ENGINE", "spacy")
                self._init_analyzer(engine_type)
                safe_logger.info(
                    f"PresidioDeIdentificationService initialized with NER engine: {engine_type}"
                )
            except Exception as e:
                safe_logger.error(f"Failed to initialize Presidio: {e}")

    def _init_analyzer(self, engine_type: str):
        """Initialize the analyzer engine with the specified NER backend."""
        if engine_type == "transformers":
            self._init_transformers_engine()
        else:
            self._init_spacy_engine()

    def _init_spacy_engine(self):
        """Initialize with spaCy NLP engine (default)."""
        try:
            model_name = getattr(settings, "PRESIDIO_NER_MODEL", "en_core_web_lg")
            nlp_config = {
                "nlp_engine_name": "spacy",
                "models": [{"lang_code": "en", "model_name": model_name}],
            }
            provider = NlpEngineProvider(nlp_configuration=nlp_config)
            nlp_engine = provider.create_engine()
            self.analyzer = AnalyzerEngine(nlp_engine=nlp_engine)
            self.active_ner_engine = "spacy"
            self.active_model_name = model_name
            safe_logger.info(f"Presidio spaCy engine initialized with model: {model_name}")
        except Exception as e:
            safe_logger.error(f"Failed to initialize spaCy engine: {e}")
            raise

    def _init_transformers_engine(self):
        """Initialize with HuggingFace transformers engine (e.g. obi/deid_roberta_i2b2)."""
        try:
            model_name = getattr(settings, "PRESIDIO_TRANSFORMER_MODEL", "obi/deid_roberta_i2b2")
            
            nlp_config = {
                "nlp_engine_name": "transformers",
                "models": [{
                    "lang_code": "en",
                    "model_name": {
                        "spacy": "en_core_web_sm",
                        "transformers": model_name,
                    },
                }],
            }
            
            nlp_engine = NlpEngineProvider(nlp_configuration=nlp_config).create_engine()
            self.analyzer = AnalyzerEngine(nlp_engine=nlp_engine)
            self.active_ner_engine = "transformers"
            self.active_model_name = model_name
            safe_logger.info(f"Presidio transformers engine initialized with model: {model_name}")
        except Exception as e:
            safe_logger.error(f"Failed to initialize transformers engine: {e}")
            # Fallback to spacy
            safe_logger.warning("Falling back to spaCy engine")
            self._init_spacy_engine()

    def switch_ner_engine(self, engine_type: str) -> dict:
        """
        Switch the NER engine at runtime.
        
        Args:
            engine_type: "spacy" or "transformers"
            
        Returns:
            dict with status info
        """
        if engine_type not in NER_MODEL_REGISTRY:
            return {"success": False, "error": f"Unknown engine: {engine_type}. Use 'spacy' or 'transformers'."}
        
        if engine_type == self.active_ner_engine:
            return {
                "success": True,
                "message": f"Already using {engine_type}",
                "active_engine": self.active_ner_engine,
                "active_model": self.active_model_name,
            }
        
        try:
            self._init_analyzer(engine_type)
            return {
                "success": True,
                "message": f"Switched to {engine_type} engine",
                "active_engine": self.active_ner_engine,
                "active_model": self.active_model_name,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_engine_info(self) -> dict:
        """Return current NER engine info and available models."""
        return {
            "active_engine": self.active_ner_engine,
            "active_model": self.active_model_name,
            "available_models": NER_MODEL_REGISTRY,
            "presidio_available": PRESIDIO_AVAILABLE,
        }

    def de_identify_for_summary(
        self,
        db: Session,
        case_id: str,
        user_id: str,
        patient_name: str,
        timeline: List[Dict],
        clinical_data: Dict,
        red_flags: List[Dict],
        case_metadata: Optional[Dict] = None,
    ) -> Tuple[Dict, str]:
        """
        Main entry point: De-identify all data before sending to Tier 2 (Claude).

        Returns:
            (de_identified_payload, vault_id)

        Raises:
            PHILeakageError: If pre-flight validation detects PHI in final payload
        """
        safe_logger.info(f"Starting de-identification for case {case_id}")

        case_metadata = case_metadata or {}

        # Step 1: Generate date shift offset
        shift_days = random.randint(
            getattr(settings, "DATE_SHIFT_MIN_DAYS", 0),
            getattr(settings, "DATE_SHIFT_MAX_DAYS", 30),
        )

        # Step 2: Collect known PHI (deterministic) 
        known_phi = self._collect_known_phi(patient_name, case_metadata)

        # Step 3: Generate unique UUID12 tokens (1:1 mapping)
        token_map = self._generate_tokens(known_phi)

        # Step 4: Replace known PHI in structured data (deterministic)
        de_id_clinical_data = self._replace_known_phi(
            deepcopy(clinical_data), token_map
        )
        de_id_timeline = self._replace_known_phi(deepcopy(timeline), token_map)
        de_id_red_flags = self._replace_known_phi(deepcopy(red_flags), token_map)

        # Step 5: Shift dates (structure-aware with field-path tracking)
        shifted_fields = []
        de_id_clinical_data, clinical_shifts = self._shift_dates_structured(
            de_id_clinical_data, shift_days, path="clinical_data"
        )
        de_id_timeline, timeline_shifts = self._shift_dates_structured(
            de_id_timeline, shift_days, path="timeline"
        )
        de_id_red_flags, red_flags_shifts = self._shift_dates_structured(
            de_id_red_flags, shift_days, path="red_flags"
        )
        shifted_fields.extend(clinical_shifts + timeline_shifts + red_flags_shifts)

        # Step 6: Presidio scan on free-text fields (catches leaks)
        de_id_clinical_data = self._presidio_scan_free_text(
            de_id_clinical_data, token_map
        )
        de_id_timeline = self._presidio_scan_free_text(de_id_timeline, token_map)
        de_id_red_flags = self._presidio_scan_free_text(de_id_red_flags, token_map)

        # Step 7: Build de-identified payload
        de_id_payload = {
            "clinical_data": de_id_clinical_data,
            "timeline": de_id_timeline,
            "red_flags": de_id_red_flags,
        }

        # Step 8: Pre-flight validation (fail-closed)
        if getattr(settings, "ENABLE_PREFLIGHT_VALIDATION", True):
            try:
                phi_validator.validate_payload(
                    payload=de_id_payload,
                    known_phi_values=known_phi,
                    case_id=case_id,
                    allow_tokens=True,
                )
            except PHILeakageError as e:
                safe_logger.error(f"Pre-flight validation failed for case {case_id}: {e}")
                raise

        # Step 9: Store in Privacy Vault
        vault_entry = PrivacyVault(
            case_id=case_id,
            user_id=user_id,
            date_shift_days=shift_days,
            token_map=token_map,
            shifted_fields=shifted_fields,
        )
        db.add(vault_entry)
        db.commit()
        db.refresh(vault_entry)

        safe_logger.info(
            f"De-identification complete for case {case_id}: "
            f"{len(token_map)} tokens, {len(shifted_fields)} date shifts, vault_id={vault_entry.id}"
        )

        return de_id_payload, vault_entry.id

    def re_identify_summary(
        self, db: Session, vault_id: str, summary_text: str
    ) -> str:
        """
        Re-identify summary text from Claude using vault mappings.

        Args:
            db: Database session
            vault_id: Privacy vault ID
            summary_text: De-identified summary from Claude

        Returns:
            Re-identified summary with original PHI restored
        """
        # Load vault
        vault = db.query(PrivacyVault).filter(PrivacyVault.id == vault_id).first()
        if not vault:
            safe_logger.error(f"Vault {vault_id} not found")
            return summary_text

        re_id_text = summary_text

        # Step 1: Replace tokens with original values
        for token, original_value in vault.token_map.items():
            re_id_text = re_id_text.replace(token, original_value)

        # Step 2: Reverse date shifts (best-effort for ISO dates in text)
        # Note: We don't use shifted_fields here because Claude may rephrase dates
        # This is intentional - narrative text doesn't need perfect date reversal
        re_id_text = self._reverse_dates_in_text(re_id_text, vault.date_shift_days)

        safe_logger.info(f"Re-identification complete for vault {vault_id}")
        return re_id_text

    # ========================================
    # Helper Methods
    # ========================================

    def _collect_known_phi(
        self, patient_name: str, case_metadata: Dict
    ) -> Dict[str, str]:
        """
        Collect known PHI values from inputs.

        Returns Dict mapping PHI value → entity type
        """
        known_phi = {}

        # Patient name
        if patient_name:
            known_phi[patient_name] = "PERSON"
            # Also tokenize first/last name separately to avoid substring issues
            name_parts = patient_name.split()
            if len(name_parts) >= 2:
                known_phi[name_parts[0]] = "PERSON"  # First name
                known_phi[name_parts[-1]] = "PERSON"  # Last name

        # Case number (based on policy)
        if getattr(settings, "TREAT_CASE_NUMBER_AS_PHI", True):
            case_number = case_metadata.get("case_number")
            if case_number:
                known_phi[str(case_number)] = "ID"

        # Facility
        facility = case_metadata.get("facility") or case_metadata.get("facility_name")
        if facility:
            known_phi[facility] = "ORGANIZATION"

        # Provider (if available)
        provider = case_metadata.get("provider") or case_metadata.get("provider_name")
        if provider:
            known_phi[provider] = "PERSON"

        safe_logger.info(f"Collected {len(known_phi)} known PHI values")
        return known_phi

    def _generate_tokens(self, known_phi: Dict[str, str]) -> Dict[str, str]:
        """
        Generate unique UUID12 tokens for known PHI.

        Returns Dict mapping token → original value (reverse of known_phi)
        Format: [[TYPE::uuid12]] where uuid12 is 48-bit (12 hex chars)
        """
        token_map = {}
        uuid_length = getattr(settings, "TOKEN_UUID_LENGTH", 12)

        for phi_value, entity_type in known_phi.items():
            # Generate unique UUID token
            token_uuid = uuid.uuid4().hex[:uuid_length]
            token = f"[[{entity_type}::{token_uuid}]]"

            # Store mapping (token → original)
            token_map[token] = phi_value

        safe_logger.info(f"Generated {len(token_map)} UUID{uuid_length} tokens")
        return token_map

    def _replace_known_phi(self, data: Any, token_map: Dict[str, str]) -> Any:
        """
        Recursively replace known PHI values with tokens in structured data.

        This is DETERMINISTIC - we replace exact values, not using Presidio.
        """
        if isinstance(data, dict):
            result = {}
            for key, value in data.items():
                # Recursively process nested structures
                result[key] = self._replace_known_phi(value, token_map)
            return result

        elif isinstance(data, list):
            return [self._replace_known_phi(item, token_map) for item in data]

        elif isinstance(data, str):
            # Replace all known PHI values in this string
            result = data
            for token, original_value in token_map.items():
                # Use whole-word replacement to avoid partial matches
                result = re.sub(
                    r'\b' + re.escape(original_value) + r'\b',
                    token,
                    result,
                    flags=re.IGNORECASE
                )
            return result

        else:
            return data

    def _shift_dates_structured(
        self, data: Any, shift_days: int, path: str = ""
    ) -> Tuple[Any, List[Dict]]:
        """
        Recursively shift dates in structured data with field-path tracking.

        Returns: (shifted_data, shifted_fields)
        where shifted_fields = [{"path": "...", "original": "...", "shifted": "..."}, ...]
        """
        shifted_fields = []

        def _shift_recursive(obj, current_path):
            if isinstance(obj, dict):
                result = {}
                for key, value in obj.items():
                    field_path = f"{current_path}.{key}" if current_path else key
                    
                    # Check if this is a date field
                    if self._is_date_field(key) and isinstance(value, str):
                        shifted_value = self._shift_single_date(value, shift_days)
                        if shifted_value != value:
                            shifted_fields.append({
                                "path": field_path,
                                "original": value,
                                "shifted": shifted_value
                            })
                        result[key] = shifted_value
                    else:
                        result[key] = _shift_recursive(value, field_path)
                return result

            elif isinstance(obj, list):
                return [
                    _shift_recursive(item, f"{current_path}[{i}]")
                    for i, item in enumerate(obj)
                ]

            else:
                return obj

        shifted_data = _shift_recursive(data, path)
        return shifted_data, shifted_fields

    def _is_date_field(self, field_name: str) -> bool:
        """Check if field name suggests it contains a date"""
        field_lower = field_name.lower()
        return any(keyword in field_lower for keyword in DATE_FIELD_KEYWORDS)

    def _shift_single_date(self, date_str: str, shift_days: int) -> str:
        """Shift a single date string"""
        try:
            # Try common date formats
            for fmt in ["%Y-%m-%d", "%m/%d/%Y", "%Y-%m-%d %H:%M:%S"]:
                try:
                    dt = datetime.strptime(date_str, fmt)
                    shifted_dt = dt + timedelta(days=shift_days)
                    return shifted_dt.strftime(fmt)
                except ValueError:
                    continue
            # If no format matches, return as-is
            return date_str
        except Exception:
            return date_str

    def _presidio_scan_free_text(
        self, data: Any, token_map: Dict[str, str]
    ) -> Any:
        """
        Scan free-text fields with Presidio to catch any PHI leaks.
        
        Recursively traverses the data structure. If a field name matches FREE_TEXT_FIELDS,
        it runs Presidio analysis and replaces detected entities with tokens.
        Updates token_map with any new entities found.
        """
        if not self.analyzer:
            return data

        def _scan_recursive(obj):
            if isinstance(obj, dict):
                for key, value in obj.items():
                    # Check if this is a free-text field
                    if isinstance(value, str) and key.lower() in FREE_TEXT_FIELDS:
                        self._process_single_string(obj, key, value, token_map)
                    
                    # Recurse
                    elif isinstance(value, (dict, list)):
                        _scan_recursive(value)
                        
            elif isinstance(obj, list):
                for item in obj:
                    _scan_recursive(item)

        _scan_recursive(data)
        return data

    def _process_single_string(
        self, parent_obj: Dict, key: str, text: str, token_map: Dict[str, str]
    ):
        """Analyze and redact a single string value"""
        try:
            results = self.analyzer.analyze(text=text, language='en')
            if not results:
                return

            # Sort results by start index descending to replace from end
            results.sort(key=lambda x: x.start, reverse=True)
            
            new_text = text
            for res in results:
                # Only handle high-confidence sensitive types
                if res.score < 0.4:
                    continue
                    
                entity_text = text[res.start:res.end]
                entity_type = res.entity_type
                
                # Check if we already have a token for this EXACT value
                existing_token = None
                for tok, val in token_map.items():
                    if val == entity_text:
                        existing_token = tok
                        break
                
                if not existing_token:
                    # Generate new token
                    token_uuid = uuid.uuid4().hex[:12]
                    existing_token = f"[[{entity_type}::{token_uuid}]]"
                    token_map[existing_token] = entity_text
                
                # Verify token format to avoid double-tokenizing
                if "[[" in entity_text and "]]" in entity_text:
                    continue  # Already tokenized

                # Replace in string
                new_text = new_text[:res.start] + existing_token + new_text[res.end:]
            
            parent_obj[key] = new_text

        except Exception as e:
            safe_logger.warning(f"Presidio scan failed for field {key}: {e}")

    def _reverse_dates_in_text(self, text: str, shift_days: int) -> str:
        """
        Best-effort reversal of ISO dates in narrative text.

        Note: Claude may rephrase dates, so this is approximate.
        Structure-aware reversal uses shifted_fields for precision.
        """
        if shift_days == 0:
            return text

        # Find all ISO-style dates (YYYY-MM-DD)
        date_pattern = r'\b(\d{4})-(\d{2})-(\d{2})\b'

        def reverse_date(match):
            try:
                date_str = match.group(0)
                dt = datetime.strptime(date_str, "%Y-%m-%d")
                reversed_dt = dt - timedelta(days=shift_days)
                return reversed_dt.strftime("%Y-%m-%d")
            except Exception:
                return match.group(0)

        return re.sub(date_pattern, reverse_date, text)


# Singleton instance
presidio_deidentification_service = PresidioDeIdentificationService()
