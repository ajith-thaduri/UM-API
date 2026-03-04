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

import asyncio
import json
import random
import re
import uuid
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.privacy_vault import PrivacyVault
from app.models.presidio_engine import PresidioEngine
from app.db.session import SessionLocal
from app.services.phi_validator import phi_validator, PHILeakageError
from app.services.date_shift_service import date_shift_service
from app.services.presidio_recognizers import (
    MRNRecognizer,
    TimeRecognizer,
    HospitalRecognizer,
    DoctorRecognizer,
    FullNameRecognizer,
    LocationRecognizer,
    DOBRecognizer,
    StreetRecognizer,
    ZipRecognizer,
    NPIRecognizer,
    InsuranceRecognizer,
    SSNRecognizer,
    EmergencyContactRecognizer,
    AccountRecognizer,
    IPRecognizer,
    VehiclePlateRecognizer,
    PassportRecognizer,
    DriversLicenseRecognizer,
    MACAddressRecognizer,
    SubAddressRecognizer,
    AgeRecognizer,
    CoordinateRecognizer,
    EmployerRecognizer,
    StateRecognizer,
    CountryRecognizer,
    CreditCardRecognizer
)
from app.utils.safe_logger import get_safe_logger
from presidio_anonymizer.entities import OperatorConfig

safe_logger = get_safe_logger(__name__)

try:
    from presidio_analyzer import AnalyzerEngine
    from presidio_anonymizer import AnonymizerEngine
    from presidio_analyzer.nlp_engine import NlpEngineProvider

    PRESIDIO_AVAILABLE = True
except ImportError:
    PRESIDIO_AVAILABLE = False
    safe_logger.warning("Presidio not available - de-identification disabled")

# Transformer model label -> Presidio entity mapping
# Maps medical PHI categories to standard Presidio types
ROBERTA_LABEL_TO_PRESIDIO = {
    # Common labels
    "PATIENT": "PERSON",
    "STAFF": "PERSON",
    "HCW": "PERSON",          # Stanford label (Healthcare Worker)
    "AGE": "AGE",
    "DATE": "DATE_TIME",
    "PHONE": "PHONE_NUMBER",
    "EMAIL": "EMAIL_ADDRESS",
    "ID": "ID",
    "HOSP": "ORGANIZATION",      # i2b2 label
    "HOSPITAL": "ORGANIZATION",  # Stanford label
    "VENDOR": "ORGANIZATION",    # Stanford label
    "PATORG": "ORGANIZATION",
    "LOC": "LOCATION",
    "IP": "PII",                 # IP addresses
    "URL": "PII",                # URLs/Websites
    "OTHERPHI": "NRP",
}

# Entity type normalization map
# Normalizes medical-specific entity types to standard Presidio types
# This ensures consistent tokenization (e.g., "John Doe" always becomes [[PERSON-01]])
ENTITY_TYPE_NORMALIZATION = {
    # --- Unified Person Category ---
    "PATIENT": "PERSON",
    "PATIENT_FULL_NAME": "PERSON",
    "PERSON": "PERSON",
    "PROVIDER": "PERSON",
    "DOCTOR": "PERSON",
    "STAFF": "PERSON",
    "HCW": "PERSON",
    "USER": "PERSON",
    "EMERGENCY_CONTACT": "PERSON",
    
    # --- Unified Organization Category ---
    "HOSPITAL": "ORGANIZATION",
    "HOSP": "ORGANIZATION",
    "FACILITY": "ORGANIZATION",
    "CLINIC": "ORGANIZATION",
    "PHARMACY": "ORGANIZATION",
    "VENDOR": "ORGANIZATION",
    "PATORG": "ORGANIZATION",
    "ORGANIZATION": "ORGANIZATION",
    
    # --- Unified ID Category ---
    "MRN": "ID",
    "NPI": "ID",
    "SSN": "ID",
    "US_SSN": "ID",
    "INSURANCE_ID": "ID",
    "POLICY_NUMBER": "ID",
    "ACCOUNT_NUMBER": "ID",
    "PASSPORT": "ID",
    "DRIVERS_LICENSE": "ID",
    "VEHICLE_PLATE": "ID",
    "DEVICE_ID": "ID",
    "NATIONAL_ID": "ID",
    "ID": "ID",
    
    # --- Unified Location Category ---
    "STREET_ADDRESS": "LOCATION",
    "CITY": "LOCATION",
    "CITY_FACILITY": "LOCATION",
    "ZIP_CODE": "LOCATION",
    "LOCATION": "LOCATION",
    "ADDRESS": "LOCATION",
    
    # --- Unified Communication/Internet Category ---
    "PHONE_NUMBER": "PHONE_NUMBER",
    "FAX": "PHONE_NUMBER",
    "EMAIL_ADDRESS": "EMAIL_ADDRESS",
    "IP_ADDRESS": "IP_ADDRESS",
    "URL": "PII",
    "WEBSITE": "PII",
    
    # --- Other Categories ---
    "DATE_TIME": "DATE_TIME",
    "TIME": "DATE_TIME",
    "AGE": "AGE",
    "SEX": "AGE",
    "COORDINATE": "COORDINATE",
}

# --- NER False Positive Block-lists ---
# Structural/header labels that must be an exact match to avoid blocking real names
NER_EXACT_BLOCKLIST = {
    "patient name", "patient", "admission date", "discharge date",
    "medical record", "mrn", "case number", "account number", "health plan",
    "npi", "provider", "doctor", "staff", "attending", "emergency contact",
    "secondary email", "alias", "alias used", "alternative name", "alt name",
    "prior records", "result flag", "date test", "physician", "date of birth",
    "dob", "ssn", "social security",
    "policy number", "group number", "health plan id", "admission",
    "discharge", "medical record number", "mrn number", "patient info",
    "physician phone", "physician email", "physician name",
    "physician fax", "patient phone", "patient email",
    "patient address", "emergency phone",
    "emergency email", "contact phone", "contact email",
    "home phone", "mobile phone", "work phone",
    "home address", "work address", "mailing address",
    "primary phone", "secondary phone", "primary email",
    "clinical summary", "discharge summary", "admission summary",
    "insurance information",
    "billing information", "contact information",
    # Device / equipment labels
    "pacemaker model", "serial number", "device id", "model number",
}

# Clinical phrases/eponyms that can be matched anywhere inside an entity
NER_PHRASE_BLOCKLIST = {
    # Headers that might get grouped with other words
    "medical encounter details", "encounter information", "patient demographics",
    "hospital encounter", "information hospital", "encounter details",
    # Clinical eponyms / disease names that get mis-tagged as PERSON
    "parkinson", "parkinson's", "crohn", "crohn's", "raynaud", "raynaud's",
    "alzheimer", "alzheimer's", "huntington", "huntington's", "glasgow coma",
    "glasgow", "medtronic", "azure", "medicare",
}

# --- NER Quality Validation ---

# Comprehensive US phone number pattern (handles +1 and 1-)
_PHONE_REGEX = re.compile(
    r'^(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}$'
)

# Valid street address: must START with a digit (optional ordinal) and END with a street suffix keyword
_STREET_REGEX = re.compile(
    r'^\d{1,6}(?:st|nd|rd|th)?\s+(?:[A-Za-z0-9]+\s+){0,5}'
    r'(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|'
    r'Drive|Dr|Terrace|Way|Court|Ct|Circle|Cir|Place|Pl|'
    r'Highway|Hwy|Parkway|Pkwy)\b',
    re.IGNORECASE
)

# Words that indicate a clinical narrative falsely detected as a street address
_CLINICAL_CONTEXT_WORDS = {
    "under", "care", "patient", "admitted", "discharged",
    "presented", "history", "physician", "services"
}

# Maximum character span length before we consider it a multi-name block
_MAX_ENTITY_SPAN = 50

# Minimum meaningful token length (chars in the stripped span)
_MIN_ENTITY_CHARS = 3

_SUFFIX_ONLY_REGEX = re.compile(
    r'^[,()\s]*\b(?:MD|DO|PhD|NP|PA|RN|LPN|FNP|DNP|JD|MSW|LCSW|FACS|FACC|FCCP)\b[.,()\s]*$',
    re.IGNORECASE
)

# Regex to trim from PERSON entities
_CREDENTIALS_TRIM_REGEX = re.compile(
    r'[,.\s]+\b(?:MD|DO|PhD|RN|NP|PA|LPN|FNP|DNP|JD|MSW|LCSW|FACS|FACC|FCCP|PGY-?\d)\b(?:\.?\s*|$)', 
    re.IGNORECASE
)
_HONORIFIC_PREFIX_REGEX = re.compile(
    r'^(?:Mr\.|Ms\.|Mrs\.|Miss|Dr\.|Prof\.|Pt\.)\s+', 
    re.IGNORECASE
)

_USERNAME_REGEX = re.compile(r'^[a-z][a-z0-9._-]*[0-9._-]+[a-z0-9._-]*$', re.IGNORECASE)
_FILENAME_REGEX = re.compile(r'\.\w{2,5}$', re.IGNORECASE)

_MAX_SPAN_BY_TYPE = {
    "PERSON": 40,
    "ORGANIZATION": 60,
    "LOCATION": 50,
}
_DEFAULT_MAX_SPAN = 60

# --- Clinical Relevance Tiers ---

# Entity types that get numbered tokens (AI needs to distinguish these)
TOKENIZE_TYPES = {"PERSON", "ORGANIZATION"}

# Entity types stripped to [[REDACTED]] (zero clinical value for summary)
STRIP_TYPES = {
    "ID", "PHONE_NUMBER", "EMAIL_ADDRESS", "US_SSN", "SSN",
    "LOCATION", "IP_ADDRESS", "URL", "PII", "ADDRESS",
    "INSURANCE_ID", "NPI", "MRN", "PASSPORT",
    "DRIVERS_LICENSE", "DEVICE_ID", "VEHICLE_PLATE",
    "ACCOUNT_NUMBER", "FAX", "NATIONAL_ID", "WEBSITE",
    "ZIP_CODE", "STREET_ADDRESS", "CITY", "MAC_ADDRESS", "SUB_ADDRESS",
    "COORDINATE",
}


def normalize_entity_type(entity_type: str) -> str:
    """
    Normalize entity type to standard Presidio category.
    Example: PATIENT_FULL_NAME → PERSON, HOSPITAL → ORGANIZATION
    """
    return ENTITY_TYPE_NORMALIZATION.get(entity_type, entity_type)

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

# Entity priority map (higher number = higher priority)
# Ensures custom medical entities win over generic NER labels
ENTITY_PRIORITY = {
    "PROVIDER": 100,
    "NPI": 95,
    "INSURANCE_ID": 92,
    "PATIENT_FULL_NAME": 90,
    "SSN": 98,
    "IP_ADDRESS": 95,
    "MRN": 85,
    "STREET_ADDRESS": 82,
    "ZIP_CODE": 78,
    "HOSPITAL": 75,
    "CITY": 80,
    "CITY_FACILITY": 80,
    "PERSON": 50,
    "LOCATION": 45,
    "ORGANIZATION": 40,
    "ID": 35,
    "PHONE_NUMBER": 30,
}
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
        self.active_ner_engine: str = "transformers"
        self.active_model_name: str = "StanfordAIMI/stanford-deidentifier-base"
        self.active_engine_id: Optional[str] = None
        self.custom_recognizers = [
            MRNRecognizer,
            TimeRecognizer,
            HospitalRecognizer,
            DoctorRecognizer,
            FullNameRecognizer,
            LocationRecognizer,
            DOBRecognizer,
            StreetRecognizer,
            ZipRecognizer,
            NPIRecognizer,
            InsuranceRecognizer,
            IPRecognizer,
            SSNRecognizer,
            EmergencyContactRecognizer,
            AccountRecognizer,
            VehiclePlateRecognizer,
            PassportRecognizer,
            DriversLicenseRecognizer,
            MACAddressRecognizer,
            SubAddressRecognizer,
            AgeRecognizer,
            CoordinateRecognizer,
            EmployerRecognizer,
            StateRecognizer,
            CountryRecognizer,
            CreditCardRecognizer
        ]

        if PRESIDIO_AVAILABLE:
            self.anonymizer = AnonymizerEngine()
            self._load_active_engine_from_db()
            safe_logger.info(
                f"PresidioDeIdentificationService initialized with NER engine: {self.active_ner_engine} "
                f"({self.active_model_name})"
            )

    _STANFORD_MODEL = "StanfordAIMI/stanford-deidentifier-base"

    def _load_active_engine_from_db(self):
        """Load the active engine from DB for audit/logging only.

        Regardless of what the DB says, case processing ALWAYS uses the Stanford
        AIMI transformers model.  spaCy is intentionally never used here.
        """
        db = SessionLocal()
        try:
            active_engine = db.query(PresidioEngine).filter(PresidioEngine.is_active == True).first()

            if active_engine:
                self.active_engine_id = active_engine.id
                if active_engine.engine_type != "transformers" or active_engine.model_name != self._STANFORD_MODEL:
                    safe_logger.warning(
                        f"DB active engine is '{active_engine.name}' ({active_engine.model_name}), "
                        f"but case processing enforces Stanford AIMI only. Ignoring DB selection."
                    )
                else:
                    safe_logger.info(f"DB engine confirmed: {active_engine.name} ({active_engine.model_name})")
            else:
                self.active_engine_id = None
                safe_logger.info("No active engine in DB — using Stanford AIMI (default).")

            # Always use Stanford AIMI for case processing — no spaCy, no other model.
            self.active_ner_engine = "transformers"
            self.active_model_name = self._STANFORD_MODEL
            self._init_transformers_engine()
            self._register_custom_recognizers()
        except Exception as e:
            safe_logger.error(
                f"Failed to initialize Stanford AIMI engine: {e}. "
                "De-identification is unavailable — case processing will be blocked."
            )
            raise RuntimeError(
                f"Presidio Stanford AIMI engine failed to initialize: {e}"
            ) from e
        finally:
            db.close()

    def _init_analyzer(self, engine_type: str):
        """Initialize the analyzer engine. Always uses transformers/Stanford AIMI."""
        self._init_transformers_engine()

    def _init_spacy_engine(self):
        """Initialize with spaCy NLP engine. Not used for case processing (Stanford AIMI only)."""
        try:
            # Use active_model_name if it's a spacy model (no /), otherwise default to en_core_web_lg
            model_name = self.active_model_name
            if not model_name or "/" in model_name:
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
        except SystemExit as e:
            # spaCy calls sys.exit() when a model is not installed/incompatible.
            # Catch it here so the worker process does not die.
            safe_logger.error(
                f"spaCy model '{self.active_model_name}' is not installed or incompatible "
                f"(spaCy raised SystemExit: {e}). Falling back to en_core_web_lg."
            )
            try:
                fallback = "en_core_web_lg"
                nlp_config = {"nlp_engine_name": "spacy", "models": [{"lang_code": "en", "model_name": fallback}]}
                provider = NlpEngineProvider(nlp_configuration=nlp_config)
                nlp_engine = provider.create_engine()
                self.analyzer = AnalyzerEngine(nlp_engine=nlp_engine)
                self.active_ner_engine = "spacy"
                self.active_model_name = fallback
                safe_logger.info(f"Presidio spaCy engine initialized with fallback model: {fallback}")
            except Exception as fallback_err:
                safe_logger.error(f"Fallback spaCy engine also failed: {fallback_err}")
                raise RuntimeError(f"Cannot initialize Presidio spaCy engine: {fallback_err}") from fallback_err
        except Exception as e:
            safe_logger.error(f"Failed to initialize spaCy engine: {e}")
            raise

    def _init_transformers_engine(self):
        """Initialize with Stanford AIMI HuggingFace transformers engine.

        This is the ONLY model used for case processing.  No spaCy fallback.
        A failure here is a hard error — workers should not process cases with
        a degraded / wrong model.
        """
        model_name = self._STANFORD_MODEL

        nlp_config = {
            "nlp_engine_name": "transformers",
            "models": [{
                "lang_code": "en",
                "model_name": {
                    "spacy": "en_core_web_sm",
                    "transformers": model_name,
                },
                # Must be inside the model entry — Presidio's NlpEngineProvider passes
                # labels_to_ignore to NerModelConfiguration at the per-model level, not
                # at the top level.  Placing it at the top level is silently ignored,
                # which is why the "Entity X is not mapped" warning persisted.
                "labels_to_ignore": ["VENDOR", "PATORG", "HCW", "HOSP", "OTHERPHI"],
            }],
            "model_to_presidio_entity_mapping": ROBERTA_LABEL_TO_PRESIDIO,
        }

        nlp_engine = NlpEngineProvider(nlp_configuration=nlp_config).create_engine()
        self.analyzer = AnalyzerEngine(nlp_engine=nlp_engine)
        self.active_ner_engine = "transformers"
        self.active_model_name = model_name
        safe_logger.info(f"Presidio transformers engine initialized with model: {model_name}")

    def _register_custom_recognizers(self):
        """Register all custom medical PHI recognizers into the current analyzer instance."""
        if not self.analyzer:
            return
            
        # Get list of currently registered recognizer names
        registered_names = []
        for r in self.analyzer.registry.recognizers:
            if hasattr(r, 'name'):
                registered_names.append(r.name)
            
        for recognizer in self.custom_recognizers:
            # Check if already registered to avoid duplicates
            rec_name = recognizer.name if hasattr(recognizer, 'name') else None
            if rec_name and rec_name not in registered_names:
                self.analyzer.registry.add_recognizer(recognizer)
                safe_logger.debug(f"Registered custom recognizer: {rec_name}")
        
        safe_logger.info(f"Custom HIPAA recognizers registered. Total: {len(self.custom_recognizers)}")

    def switch_ner_engine(self, engine_type: str = None, model_id: str = None) -> Dict[str, Any]:
        """
        Switch the DB active engine record (for Presidio Lab / audit purposes only).

        NOTE: Case processing is permanently locked to Stanford AIMI.  Calling this
        method updates the DB record and reloads the service, but _load_active_engine_from_db
        will always enforce Stanford AIMI regardless of the DB selection.

        Args:
            engine_type: legacy type filter (ignored for case processing)
            model_id: UUID of the model in presidio_engines table

        Returns:
            dict with status info
        """
        if not PRESIDIO_AVAILABLE:
            return {"status": "error", "message": "Presidio not available"}

        db = SessionLocal()
        try:
            target_engine = None
            
            if model_id:
                # Switch by ID
                target_engine = db.query(PresidioEngine).filter(PresidioEngine.id == model_id).first()
                if not target_engine:
                    return {"status": "error", "message": f"Model ID {model_id} not found"}
            
            elif engine_type:
                # Legacy switch by type - find first available matching type
                target_engine = db.query(PresidioEngine).filter(PresidioEngine.engine_type == engine_type).first()
                if not target_engine:
                    return {"status": "error", "message": f"No engine found for type {engine_type}"}

            if not target_engine:
                return {"status": "error", "message": "No model specified"}

            # Update DB to set this as active
            # 1. Set all to inactive
            db.query(PresidioEngine).update({PresidioEngine.is_active: False})
            # 2. Set target to active
            target_engine.is_active = True
            db.commit()
            
            # Reload in service
            self._load_active_engine_from_db()

            return {
                "status": "success",
                "active_engine": self.active_ner_engine,
                "active_model": self.active_model_name,
                "active_id": self.active_engine_id,
                "message": f"Switched to {target_engine.name}"
            }
            
        except Exception as e:
            db.rollback()
            safe_logger.error(f"Failed to switch engine: {e}")
            return {"status": "error", "message": str(e)}
        finally:
            db.close()

    def get_engine_info(self) -> Dict[str, Any]:
        """Return current NER engine info and available models from DB."""
        if not PRESIDIO_AVAILABLE:
             return {"status": "Presidio not available", "available_models": [], "active_engine": None}
             
        db = SessionLocal()
        try:
            available_models = db.query(PresidioEngine).all()
            
            return {
                "active_engine": self.active_ner_engine,
                "active_model": self.active_model_name,
                "active_id": self.active_engine_id,
                "available_models": [
                    {
                        "id": m.id,
                        "name": m.name,
                        "engine_type": m.engine_type,
                        "model_name": m.model_name,
                        "description": m.description,
                        "is_active": m.is_active
                    } for m in available_models
                ],
                "presidio_available": PRESIDIO_AVAILABLE,
            }
        finally:
            db.close()

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
        score_threshold: Optional[float] = None,
        document_chunks: Optional[List[str]] = None
    ) -> Tuple[Dict, str, Dict[str, str]]:
        """
        Main entry point: De-identify all data before sending to Tier 2 (Claude).

        Returns:
            (de_identified_payload, vault_id)

        Raises:
            PHILeakageError: If pre-flight validation detects PHI in final payload
        """
        safe_logger.info(f"Starting de-identification for case {case_id}")

        case_metadata = case_metadata or {}
        
        # Use config threshold if not provided
        if score_threshold is None:
            score_threshold = settings.PRESIDIO_FREE_TEXT_THRESHOLD

        # Step 1: Generate date shift offset
        shift_days = random.randint(
            getattr(settings, "DATE_SHIFT_MIN_DAYS", 1), # Force at least 1 day for testing
            getattr(settings, "DATE_SHIFT_MAX_DAYS", 30),
        )
        safe_logger.info(f"Generated shift_days={shift_days} for case {case_id}")

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
            de_id_clinical_data, token_map, shift_days=shift_days, score_threshold=score_threshold
        )
        de_id_timeline = self._presidio_scan_free_text(
            de_id_timeline, token_map, shift_days=shift_days, score_threshold=score_threshold
        )
        de_id_red_flags = self._presidio_scan_free_text(
            de_id_red_flags, token_map, shift_days=shift_days, score_threshold=score_threshold
        )

        # Step 6.5: De-identify document chunks (if provided)
        de_id_chunks = []
        if document_chunks:
            safe_logger.info(f"De-identifying {len(document_chunks)} document chunks for case {case_id}")
            for i, chunk_text in enumerate(document_chunks):
                # Apply the generic string replacement logic
                de_id_chunk_text = self._replace_in_string(chunk_text)

                # Shift dates in chunk text (regex first)
                de_id_chunk_text = self._shift_dates_in_text(de_id_chunk_text, shift_days)
                
                # Presidio scan to catch any residual PHI not in the known map
                if self.analyzer:
                    analyzed = self.analyzer.analyze(
                        text=de_id_chunk_text,
                        language="en",
                        score_threshold=score_threshold
                    )
                    
                    # Filter already tokenized spans
                    analyzed = [res for res in analyzed if "[[" not in de_id_chunk_text[res.start:res.end]]
                    
                    if analyzed:
                        # For residual PHI: 
                        # - If TOKENIZE type -> create new token
                        # - If DATE_TIME -> shift
                        # - If STRIP type -> [[REDACTED]]
                        de_id_chunk_text = self._process_residual_phi_in_string(
                            de_id_chunk_text, analyzed, token_map, shift_days, score_threshold
                        )
                
                de_id_chunks.append(de_id_chunk_text)
            
            safe_logger.info(f"Successfully de-identified {len(de_id_chunks)} document chunks")

        # Step 7: Build de-identified payload
        de_id_payload = {
            "clinical_data": de_id_clinical_data,
            "timeline": de_id_timeline,
            "red_flags": de_id_red_flags,
            "document_chunks": de_id_chunks,
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
        # Deactivate any existing active vaults for this case (e.g. reprocessing scenario).
        # The partial unique index on (case_id) WHERE is_active=TRUE enforces one active vault.
        existing_active = (
            db.query(PrivacyVault)
            .filter(PrivacyVault.case_id == case_id, PrivacyVault.is_active == True)
            .all()
        )
        for old_vault in existing_active:
            old_vault.is_active = False
        if existing_active:
            db.flush()
            safe_logger.info(f"Deactivated {len(existing_active)} old vault(s) for case {case_id}")

        vault_entry = PrivacyVault(
            case_id=case_id,
            user_id=user_id,
            date_shift_days=shift_days,
            token_map=token_map,
            shifted_fields=shifted_fields,
            is_active=True,
        )
        db.add(vault_entry)
        db.commit()
        db.refresh(vault_entry)

        safe_logger.info(
            f"De-identification complete for case {case_id}: "
            f"{len(token_map)} tokens, {len(shifted_fields)} date shifts, vault_id={vault_entry.id}"
        )

        return de_id_payload, vault_entry.id, token_map

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
    ) -> Dict[str, Any]:
        """
        Collect known PHI values and group them by 'identity'.
        
        Industry-level strategy:
        1. STRIP: Emails, Phones, MRNs, SSNs -> [[REDACTED]]
        2. TOKENIZE: Person names, Orgs -> [[PERSON-NN]], [[ORGANIZATION-NN]]
        
        Returns a dict containing:
            'strips': List of strings to be redacted
            'identities': List of dicts {type: str, canonical: str, variants: List[str]}
        """
        case_metadata = case_metadata or {}
        strips = set()
        identities = []

        # --- 1. PERSON: Patient ---
        if patient_name:
            patient_identity = {"type": "PERSON", "canonical": patient_name, "variants": set()}
            
            # 1a. Create multi-word variants (NO single names)
            parts = patient_name.split()
            if len(parts) >= 3:
                # Henry Jonathan Matthews -> Henry Matthews, Henry Jonathan
                patient_identity["variants"].add(f"{parts[0]} {parts[-1]}")
                patient_identity["variants"].add(f"{parts[0]} {parts[1]}")
            
            # 1b. Add alias and its parts
            alias = case_metadata.get("Alias Used in Prior Records") or case_metadata.get("alias")
            if alias:
                patient_identity["variants"].add(alias)
                a_parts = alias.split()
                if len(a_parts) >= 2:
                     patient_identity["variants"].add(f"{a_parts[0]} {a_parts[-1]}")
            
            patient_identity["variants"] = list(patient_identity["variants"])
            identities.append(patient_identity)

        # --- 2. PERSON: Provider ---
        provider = case_metadata.get("provider") or case_metadata.get("provider_name") or case_metadata.get("physician") or case_metadata.get("doctor")
        if provider:
            provider_identity = {"type": "PERSON", "canonical": provider, "variants": []}
            # No single-word variants for provider to avoid over-tokenization
            identities.append(provider_identity)

        # --- 3. PERSON: Emergency Contact ---
        ec_name = case_metadata.get("emergency_contact_name") or case_metadata.get("emergency_contact")
        if ec_name:
            ec_identity = {"type": "PERSON", "canonical": ec_name, "variants": set()}
            parts = ec_name.split()
            for p in parts:
                if len(p) > 2:
                    ec_identity["variants"].add(p)
            ec_identity["variants"] = list(ec_identity["variants"])
            identities.append(ec_identity)

        # --- 4. ORGANIZATION: Facility, Employer, Insurer ---
        facility = case_metadata.get("facility") or case_metadata.get("facility_name")
        if facility:
            identities.append({"type": "ORGANIZATION", "canonical": facility, "variants": []})

        for org_key in ["employer", "employer_name", "company", "company_name", 
                        "workplace", "insurance_provider", "insurance_company",
                        "payer", "payer_name", "insurer", "bank", "bank_name"]:
            org_val = case_metadata.get(org_key)
            if org_val:
                identities.append({"type": "ORGANIZATION", "canonical": org_val, "variants": []})

        # --- 5. STRIP: PII with zero clinical value ---
        strip_fields = [
            "mrn", "ssn", "case_number", "phone", "email", 
            "address", "zip", "city", "state", "insurance_id", "npi",
            "account_number", "health_plan_id", "dob",
            "passport", "license", "vehicle_plate",
            "SSN", "Medical Record Number (MRN)", "Case Number",
            "Health Plan ID", "Account Number", "NPI (Attending)"
        ]
        for field in strip_fields:
            val = case_metadata.get(field)
            if val:
                strips.add(str(val))
        
        # Also check common variations
        for k, v in case_metadata.items():
            k_lower = k.lower()
            if any(x in k_lower for x in ["email", "phone", "mobile", "home", "fax"]):
                if v: strips.add(str(v))
            if any(x in k_lower for x in ["employer", "company", "workplace", "insurer", "payer", "bank"]):
                if v and isinstance(v, str):
                    identities.append({"type": "ORGANIZATION", "canonical": v, "variants": []})

        safe_logger.info(f"Collected {len(identities)} identities and {len(strips)} strip values")
        return {
            "identities": identities,
            "strips": list(strips)
        }

    def _generate_tokens(self, data_groups: Dict[str, Any]) -> Dict[str, str]:
        """
        Generate unique counter-based tokens based on identity groups.
        
        Returns token_map: token -> canonical_value
        """
        token_map = {}
        counters = {}
        
        # We also need a local variant_map for replacement, but it's not stored in vault
        self._variant_token_map = {}
        self._strip_list = data_groups.get("strips", [])

        for group in data_groups.get("identities", []):
            entity_type = group["type"]
            canonical = group["canonical"]
            variants = group.get("variants", [])
            
            # Increment counter for this type
            current_count = counters.get(entity_type, 0) + 1
            counters[entity_type] = current_count
            
            # Format: [[TYPE-01]]
            token = f"[[{entity_type}-{current_count:02d}]]"
            
            # Store in vault map
            token_map[token] = canonical
            
            # Store in replacement map
            self._variant_token_map[canonical] = token
            for v in variants:
                # If variant is already mapped (e.g. 'Michael' in both patient and provider),
                # first one wins (usually patient).
                if v not in self._variant_token_map:
                    self._variant_token_map[v] = token

        safe_logger.info(f"Generated {len(token_map)} counter tokens for groups")
        return token_map

    def _replace_known_phi(self, data: Any, token_map: Dict[str, str]) -> Any:
        """
        Recursively replace known PHI values with tokens/redaction in structured data.
        """
        if isinstance(data, dict):
            return {k: self._replace_known_phi(v, token_map) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._replace_known_phi(item, token_map) for item in data]
        elif isinstance(data, str):
            return self._replace_in_string(data)
        return data

    def _replace_in_string(self, text: str) -> str:
        """
        Industry-level replacement strategy:
        1. HEURISTIC STRIP: Emails, URLs, Phones (regex) -> [[REDACTED]]
        2. KNOWN STRIP: MRN, SSN, explicitly provided PII -> [[REDACTED]]
        3. IDENTITIES: Replace names with [[PERSON-NN]] tokens (longest-first)
        """
        if not text:
            return text
            
        result = text
        
        # --- Stage 1: Heuristic Regex Strip (High confidence PII) ---
        # This fixes the bug where name parts corrupt emails/URLs
        
        # Emails
        result = re.sub(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', "[[REDACTED]]", result)
        # URLs
        result = re.sub(r'https?://[^\s<>"]+|www\.[^\s<>"]+', "[[REDACTED]]", result)
        # Phone numbers (US-centric, handles +1 and 1-)
        result = re.sub(r'(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}', "[[REDACTED]]", result)
        
        # --- HIPAA Hardening: Additional Safe Harbor Identifiers ---
        # SSN
        result = re.sub(r'\b\d{3}-\d{2}-\d{4}\b', "[[REDACTED]]", result)
        # MAC Address
        result = re.sub(r'\b([0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b', "[[REDACTED]]", result)
        # IPv4
        result = re.sub(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', "[[REDACTED]]", result)
        # Credit Cards
        result = re.sub(r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b', "[[REDACTED]]", result)
        # VIN
        result = re.sub(r'\b[A-HJ-NPR-Z0-9]{17}\b', "[[REDACTED]]", result)
        # Countries (Safe harbor allows, but zero utility)
        for country in ["United States", "USA", "U.S.", "U.S.A.", "United Kingdom", "UK"]:
            result = re.sub(r'\b' + re.escape(country) + r'\b', "[[REDACTED]]", result, flags=re.I)
        # Vehicle Plates (common format)
        result = re.sub(r'\b[A-Z]{2}-[A-Z]{2,4}-\d{4}\b', "[[REDACTED]]", result)
        # Passport / Driver's License (Contextual fallback)
        result = re.sub(r'\b(?:Passport|License|DL)[:\s]*[A-Z]\d{6,9}\b', "[[REDACTED]]", result, flags=re.I)
        # Sub-addresses (Apartment/Suite/Room) — catch before city/state to avoid partial overlap
        result = re.sub(r'\bAp(?:art)?(?:ment|t)?\.?\s*#?\s*\w{1,6}\b', "[[REDACTED]]", result, flags=re.I)
        result = re.sub(r'\bS(?:ui)?te\.?\s*#?\s*\w{1,6}\b', "[[REDACTED]]", result, flags=re.I)
        result = re.sub(r'\bR(?:oo)?m\.?\s*#?\s*\d{1,4}[A-Za-z]?\b', "[[REDACTED]]", result, flags=re.I)
        result = re.sub(r'\bUnit\s*#?\s*\w{1,6}\b', "[[REDACTED]]", result, flags=re.I)
        # City, State pairs (e.g. 'Springfield, IL' / 'Austin, Texas')
        _US_STATE_ABBR = (
            r'AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MA|MD|'
            r'MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|'
            r'TX|UT|VT|VA|WA|WV|WI|WY'
        )
        _US_STATE_FULL = (
            r'Alabama|Alaska|Arizona|Arkansas|California|Colorado|Connecticut|Delaware|'
            r'Florida|Georgia|Hawaii|Idaho|Illinois|Indiana|Iowa|Kansas|Kentucky|Louisiana|'
            r'Maine|Maryland|Massachusetts|Michigan|Minnesota|Mississippi|Missouri|Montana|'
            r'Nebraska|Nevada|New\s+Hampshire|New\s+Jersey|New\s+Mexico|New\s+York|'
            r'North\s+Carolina|North\s+Dakota|Ohio|Oklahoma|Oregon|Pennsylvania|'
            r'Rhode\s+Island|South\s+Carolina|South\s+Dakota|Tennessee|Texas|Utah|Vermont|'
            r'Virginia|Washington|West\s+Virginia|Wisconsin|Wyoming'
        )
        # Stage 1 regex replacement for State abbreviations removed: 
        # It was erroneously redacting 'Jane Doe, MD' as a city in Maryland. 
        # Presidio's built-in LocationRecognizer handles city/state pairs natively anyway.

        # "Springfield, Illinois" or "Austin, Texas"
        result = re.sub(
            rf'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){{0,2}},\s*(?:{_US_STATE_FULL})\b',
            "[[REDACTED]]", result
        )
        # Ages ≥ 90 (HIPAA Safe Harbor requires ages ≥ 90 to be redacted)
        def _redact_age_90plus(m):
            try:
                age_num = int(m.group(1))
                return "90+ years old" if age_num >= 90 else m.group(0)
            except (ValueError, IndexError):
                return m.group(0)
        result = re.sub(r'\b(\d{1,3})\s*years?\s*old\b', _redact_age_90plus, result, flags=re.IGNORECASE)
        
        # --- Stage 2: Known PHI / Identity Replacement ---
        replacements = []
        
        # Add strips -> [[REDACTED]]
        for s in self._strip_list:
            if s and len(s) > 3:
                replacements.append((s, "[[REDACTED]]"))
                
        # Add identity variants -> [[TYPE-NN]]
        for val, token in self._variant_token_map.items():
            if val and len(val) > 2:
                replacements.append((val, token))
                
        # Sort by length DESCENDING
        replacements.sort(key=lambda x: len(x[0]), reverse=True)
        
        for original, target in replacements:
            # Skip if we already replaced this area via Stage 1
            if original in result:
                # Use literal replacement for strips to be safe (IDs/Codes)
                if target == "[[REDACTED]]":
                    result = re.sub(re.escape(original), target, result, flags=re.IGNORECASE)
                else:
                    # Word boundary for names/identities to avoid partial matches
                    result = re.sub(r'\b' + re.escape(original) + r'\b', target, result, flags=re.IGNORECASE)
                
        return result

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

            elif isinstance(obj, str):
                return self._shift_dates_in_text(obj, shift_days)

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
        self, data: Any, token_map: Dict[str, str], shift_days: int = 0, score_threshold: Optional[float] = None
    ) -> Any:
        """
        Scan free-text fields with Presidio to catch any PHI leaks.

        Recursively traverses the data structure. If a field name matches FREE_TEXT_FIELDS,
        it runs Presidio analysis and replaces detected entities with tokens.
        Updates token_map with any new entities found.
        """
        # Use config threshold if not provided
        if score_threshold is None:
            score_threshold = settings.PRESIDIO_FREE_TEXT_THRESHOLD
        if not self.analyzer:
            return data

        def _scan_recursive(obj):
            if isinstance(obj, dict):
                for key, value in obj.items():
                    # Check if this is a free-text field
                    if isinstance(value, str) and key.lower() in FREE_TEXT_FIELDS:
                        self._process_single_string(obj, key, value, token_map, shift_days, score_threshold)
                    
                    # Recurse
                    elif isinstance(value, (dict, list)):
                        _scan_recursive(value)
                        
            elif isinstance(obj, list):
                for item in obj:
                    _scan_recursive(item)

        _scan_recursive(data)
        return data

    def _filter_email_person_overlap(self, results):
        """
        Filter out PERSON entities that overlap with EMAIL_ADDRESS entities.
        Handles cases where 'john.doe@email.com' is detected as PERSON 'john.doe'.
        """
        filtered = []
        emails = [r for r in results if r.entity_type == "EMAIL_ADDRESS"]
        
        for r in results:
            if r.entity_type == "PERSON":
                overlaps_email = any(
                    not (r.end <= e.start or r.start >= e.end)
                    for e in emails
                )
                if overlaps_email: continue
            filtered.append(r)
        return filtered

    def _sanitize_ner_results(self, results: List[Any], text: str) -> List[Any]:
        """
        Single authoritative validation gate for all NER detections.
        Applies 5 quality rules before any tokenization occurs.
        """
        if not results:
            return []

        # Pre-compute ZIP spans for Issue 2
        zip_spans = {
            (r.start, r.end)
            for r in results if r.entity_type in (
                "ZIP_CODE",
                "VEHICLE_PLATE",
                "PASSPORT",
                "DRIVERS_LICENSE",
                "NPI",
            )
        }
        # Pre-compute EMAIL spans for Issue 4
        email_spans_list = [r for r in results if r.entity_type == "EMAIL_ADDRESS"]

        sanitized = []
        for res in results:
            span_text = text[res.start:res.end]
            entity_type = res.entity_type

            # --- Block-list check (applies globally, even in Lab) ---
            is_blocked = False
            clean_entity = span_text.lower().strip(" :.,")
            if clean_entity in NER_EXACT_BLOCKLIST:
                is_blocked = True
            else:
                for block in NER_PHRASE_BLOCKLIST:
                    if re.search(rf'\b{re.escape(block)}\b', span_text, re.IGNORECASE):
                        is_blocked = True
                        break
            
            if is_blocked:
                safe_logger.debug(f"Dropping {entity_type} '{span_text}' — hit NER blocklist")
                continue

            # --- Issue 2: ZIP Code vs Phone disambiguation ---
            if entity_type == "PHONE_NUMBER":
                # Discard if same span is already classified as ZIP_CODE
                if (res.start, res.end) in zip_spans:
                    safe_logger.debug(f"Dropping PHONE_NUMBER for '{span_text}' — overlaps with ZIP_CODE span")
                    continue
                # Discard if it doesn't look like a real phone number pattern
                clean = re.sub(r'\s+', ' ', span_text.strip())
                if not _PHONE_REGEX.match(clean):
                    safe_logger.debug(f"Dropping PHONE_NUMBER '{span_text}' — does not match strict pattern")
                    continue
                # Split concatenated entities (Issue 6)
                if len(span_text) > 20:
                    safe_logger.debug(f"Dropping concatenated PHONE span '{span_text}'")
                    continue

            # --- Issue 3: Street/Date fusion ---
            if entity_type in ("STREET_ADDRESS", "ADDRESS"):
                _BARE_STREET_REGEX = re.compile(
                    r'\b(?:on|at|off|near)\s+\w.*?(?:Street|St|Avenue|Ave|Road|Rd|Blvd|Lane|Ln|Drive|Dr|Place|Pl)\b',
                    re.IGNORECASE
                )
                # Allow both full address (starts with digit) and bare street (on/at X Street)
                if not (_STREET_REGEX.match(span_text.strip()) or _BARE_STREET_REGEX.search(span_text)):
                    safe_logger.debug(f"Dropping {entity_type} for '{span_text}' — fails street pattern")
                    continue
                # Must not contain clinical narrative words (for false positive addresses)
                words_lower = set(span_text.lower().split())
                if words_lower & _CLINICAL_CONTEXT_WORDS:
                    safe_logger.debug(f"Dropping {entity_type} for '{span_text}' — contains clinical words")
                    continue

            # --- Email detected as PERSON ---
            if entity_type == "PERSON":
                # Direct @-check on the span text itself
                if "@" in span_text:
                    safe_logger.debug(f"Dropping PERSON '{span_text}' — contains email address")
                    continue
                # Overlap with any EMAIL_ADDRESS span
                overlaps_email = any(
                    not (res.end <= e.start or res.start >= e.end)
                    for e in email_spans_list
                )
                if overlaps_email:
                    safe_logger.debug(f"Dropping PERSON '{span_text}' — overlaps with email span")
                    continue
                
                # Reject spans with newlines or escaped newlines (for JSON payloads)
                if "\n" in span_text or "\\n" in span_text:
                    safe_logger.debug(f"Dropping PERSON '{span_text}' — contains newline")
                    continue

                # Username/Filename filter
                # Match against the first word or entire trimmed span
                # Usernames often appear in clinical portal logs
                test_span = span_text.strip().split()[0] if span_text.strip() else ""
                # Also check for characters that often appear in usernames but not names
                if test_span and (
                    _USERNAME_REGEX.match(test_span) or 
                    any(c.isdigit() for c in test_span) or
                    "_" in test_span
                ) and " " not in span_text:
                    safe_logger.debug(f"Dropping PERSON '{span_text}' — looks like username/id")
                    continue
                
                if _FILENAME_REGEX.search(span_text):
                    safe_logger.debug(f"Dropping PERSON '{span_text}' — looks like filename")
                    continue

            # --- Multi-name block — span too large ---
            max_span = _MAX_SPAN_BY_TYPE.get(entity_type, _DEFAULT_MAX_SPAN)
            if (res.end - res.start) > max_span:
                safe_logger.debug(f"Dropping oversized {entity_type} span ({res.end - res.start} chars)")
                continue

            # --- LOCATION Filter ---
            if entity_type in ("LOCATION", "CITY", "CITY_FACILITY", "STREET_ADDRESS"):
                # Reject pure numbers
                if re.match(r'^\d+$', span_text.strip()): continue
                # Reject time patterns in location
                if re.search(r'\b\d{1,2}\s*(?:AM|PM)\b', span_text, re.IGNORECASE): continue
                # Reject if it looks like a person with credentials (e.g. 'Jane Doe, MD' misidentified as a city in Maryland)
                if _CREDENTIALS_TRIM_REGEX.search(span_text):
                    safe_logger.debug(f"Dropping {entity_type} for '{span_text}' — matches professional credential")
                    continue

            # --- Trimming honorifics and credentials from PERSON ---
            if entity_type == "PERSON":
                # We intentionally keep prefixes (Dr., Mr., Mrs.) based on user feedback 
                # to allow full context spans like 'Dr. Jane Doe' rather than just 'Jane Doe'
                
                # Suffix (, MD)
                suf_match = _CREDENTIALS_TRIM_REGEX.search(span_text)
                if suf_match:
                    res.end = res.start + suf_match.start()
                    span_text = text[res.start:res.end]

            # --- Pre-flight: discard credential suffixes (', MD', 'PhD', etc.) ---
            clean_span = span_text.strip(" ,.()")
            if len(clean_span) < _MIN_ENTITY_CHARS:
                safe_logger.debug(f"Dropping short span '{span_text}' ({entity_type})")
                continue
            if _SUFFIX_ONLY_REGEX.match(span_text):
                safe_logger.debug(f"Dropping credential suffix '{span_text}' — not a standalone person")
                continue

            # --- SINGLE WORD PERSON FILTER ---
            # If Stanford detects a single word as PERSON with mediocre score,
            # and it's not a known identity, it's likely a false positive.
            if entity_type == "PERSON" and " " not in span_text.strip():
                 if res.score < 0.90:
                      safe_logger.debug(f"Dropping low-score single-word PERSON '{span_text}'")
                      continue

            sanitized.append(res)

        return sanitized

    def _resolve_overlapping_spans(self, results: List[Any]) -> List[Any]:
        """
        Resolves overlapping entity spans using the 'Longest Wins' strategy.
        1. Sort by span length (descending).
        2. Keep a span only if it doesn't overlap with an already kept (longer) span.
        """
        if not results:
            return []

        # Sort by length DESC, then by score DESC
        sorted_results = sorted(
            results, 
            key=lambda x: (-(x.end - x.start), -x.score)
        )

        final_results = []
        for res in sorted_results:
            # Check overlap with results already in the final list
            overlaps = False
            for kept in final_results:
                # Standard overlap check: [s1, e1] and [s2, e2]
                if not (res.end <= kept.start or res.start >= kept.end):
                    overlaps = True
                    break
            
            if not overlaps:
                final_results.append(res)
        
        # Re-sort by start position for processing
        return sorted(final_results, key=lambda x: x.start)

    def _process_single_string(
        self, parent_obj: Any, key: Any, text: str, token_map: Dict[str, str], shift_days: int = 0, score_threshold: Optional[float] = None
    ):
        """Analyze and redact a single string value using the industry-level strategy."""
        if score_threshold is None:
            score_threshold = settings.PRESIDIO_FREE_TEXT_THRESHOLD
        if not self.analyzer:
            return
            
        try:
            # 1. Analyze
            results = self.analyzer.analyze(text=text, language='en', score_threshold=score_threshold)
            if not results:
                return

            # 2. Sanitize: apply all 5 NER quality rules (ZIP/phone, street fusion, email-person, multi-name block)
            results = self._sanitize_ner_results(results, text)

            # 3. Filter already tokenized spans (those replaced by _replace_in_string)
            results = [res for res in results if "[[" not in text[res.start:res.end]]
            if not results:
                return

            # 4. Resolve overlapping spans (Longest Wins) and apply tiers
            parent_obj[key] = self._process_residual_phi_in_string(text, results, token_map, shift_days, score_threshold)

        except Exception as e:
            safe_logger.warning(f"Presidio scan failed for field {key}: {e}")

    def _process_residual_phi_in_string(
        self, text: str, analyzer_results: List[Any], token_map: Dict[str, str], shift_days: int = 0, score_threshold: float = 0.85
    ) -> str:
        """
        Process late-discovered entities (from NER) using tokenize/strip tiers.
        Updates the global token_map for TOKENIZE types.
        
        IMPORTANT: Results must be sorted in REVERSE order (end → start) before calling.
        This ensures replacements don't shift earlier positions.
        """
        if not analyzer_results:
            return text
            
        # 1. Sanitize: apply all 5 NER quality rules
        filtered = self._sanitize_ner_results(analyzer_results, text)
        
        # 2. Resolve overlaps using Longest-Wins strategy
        filtered = self._resolve_overlapping_spans(filtered)
        
        # 3. Filter by threshold (LOCATION gets lower floor of 0.80)
        # Use a small epsilon (0.005) for float precision safety
        def passes_threshold(res):
            entity_type = normalize_entity_type(res.entity_type)
            if entity_type == "LOCATION":
                return res.score >= (min(score_threshold, 0.80) - 0.005)
            return res.score >= (score_threshold - 0.005)
        filtered = [res for res in filtered if passes_threshold(res)]
        
        # 4. Replace from END to START to maintain index offsets in original text
        #    Since we make replacements to new_text using res.start/end from original text,
        #    processing in reverse order guarantees positions before current span are intact.
        filtered.sort(key=lambda x: x.start, reverse=True)
        
        new_text = text
        for res in filtered:
            # Normalize type
            raw_type = res.entity_type
            entity_type = normalize_entity_type(raw_type)
            
            # Read entity text from new_text using the same original offsets.
            # This is safe because we process in reverse order, so characters
            # at positions [res.start:res.end] haven't been touched yet.
            entity_text = new_text[res.start:res.end].strip()
            if not entity_text or len(entity_text) < 2:
                continue

            # --- TIER C: DATE HANDLING ---
            if entity_type == "DATE_TIME":
                # We trust Stage 5 (Regex) to have shifted common date formats.
                continue

            # --- TIER D: AGE HANDLING (HIPAA Safe Harbor) ---
            if entity_type == "AGE":
                try:
                    match_age = re.search(r'\d+', entity_text)
                    if match_age:
                        age_num = int(match_age.group())
                        if age_num >= 90:
                            new_text = new_text[:res.start] + "90+" + new_text[res.end:]
                        # else: Keep as-is (allowed by HIPAA for ages < 90)
                except (ValueError, AttributeError):
                    pass
                continue

            # Reclassify ID → IP_ADDRESS if matches IPv4 pattern
            if entity_type == "ID" and re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', entity_text):
                entity_type = "IP_ADDRESS"

            # --- TIER B: STRIP ---
            if entity_type in STRIP_TYPES or "@" in entity_text:
                new_text = new_text[:res.start] + "[[REDACTED]]" + new_text[res.end:]
                continue
                
            # --- TIER A: TOKENIZE ---
            if entity_type not in TOKENIZE_TYPES:
                new_text = new_text[:res.start] + "[[REDACTED]]" + new_text[res.end:]
                continue
            
            # Match or create token for this value
            existing_token = None
            for tok, val in token_map.items():
                if val == entity_text:
                    existing_token = tok
                    break
            
            if not existing_token:
                # Find next index for this type
                max_idx = 0
                prefix = f"[[{entity_type}-"
                for tok in token_map.keys():
                    if tok.startswith(prefix):
                        try:
                            match = re.search(rf'\[\[{entity_type}-(\d+)\]\]', tok)
                            if match:
                                idx = int(match.group(1))
                                if idx > max_idx: max_idx = idx
                        except (ValueError, IndexError):
                            pass
                
                existing_token = f"[[{entity_type}-{max_idx+1:02d}]]"
                token_map[existing_token] = entity_text
                
            new_text = new_text[:res.start] + existing_token + new_text[res.end:]
        
        # Post-processing: Remove trailing duplicate Hospital suffix from organization tokens
        new_text = re.sub(
            r'(\[\[[A-Z_]+-\d{2,}\]\])\s+(?:Hospital|Medical Center|Clinic|Health Center|Health System)',
            r'\1', new_text
        )
            
        return new_text

    def _shift_dates_in_text(self, text: str, shift_days: int) -> str:
        """Helper to shift dates in narrative text."""
        if not text or shift_days == 0:
            return text
        from app.services.date_shift_service import shift_dates_in_text
        return shift_dates_in_text(text, shift_days, direction=1)

    def _reverse_dates_in_text(self, text: str, shift_days: int) -> str:
        """
        Best-effort reversal of dates in narrative text using robust regex patterns.
        """
        if shift_days == 0:
            return text

        # Use the robust reidentify_summary_text from date_shift_service
        # which internally uses subtract logic (direction=-1)
        return date_shift_service.reidentify_summary_text(text, shift_days)

    # -------------------------------------------------------------------------
    # Async wrappers: run CPU-bound Presidio in a thread pool so the event loop
    # stays responsive (used by UM-Jobs workers and summary_service).
    # -------------------------------------------------------------------------

    _executor: Optional[ThreadPoolExecutor] = None

    def _get_executor(self) -> ThreadPoolExecutor:
        """Shared thread pool for Presidio (CPU-bound). Limits concurrent runs."""
        if PresidioDeIdentificationService._executor is None:
            PresidioDeIdentificationService._executor = ThreadPoolExecutor(
                max_workers=4,
                thread_name_prefix="presidio_",
            )
        return PresidioDeIdentificationService._executor

    async def de_identify_for_summary_async(
        self,
        db: Session,
        case_id: str,
        user_id: str,
        patient_name: str,
        timeline: List[Dict],
        clinical_data: Dict,
        red_flags: List[Dict],
        case_metadata: Optional[Dict] = None,
        score_threshold: Optional[float] = None,
        document_chunks: Optional[List[str]] = None,
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ) -> Tuple[Dict, str, Dict[str, str]]:
        """
        Async wrapper: runs de_identify_for_summary in a thread pool so the
        event loop is not blocked for ~30s. Use this from async code (workers,
        summary_service).
        """
        loop = loop or asyncio.get_running_loop()
        fn = partial(
            self.de_identify_for_summary,
            db=db,
            case_id=case_id,
            user_id=user_id,
            patient_name=patient_name,
            timeline=timeline,
            clinical_data=clinical_data,
            red_flags=red_flags,
            case_metadata=case_metadata,
            score_threshold=score_threshold,
            document_chunks=document_chunks,
        )
        return await loop.run_in_executor(self._get_executor(), fn)

    async def re_identify_summary_async(
        self,
        db: Session,
        vault_id: str,
        summary_text: str,
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ) -> str:
        """
        Async wrapper: runs re_identify_summary in a thread pool. Use from
        async code after receiving the LLM response.
        """
        loop = loop or asyncio.get_running_loop()
        fn = partial(self.re_identify_summary, db=db, vault_id=vault_id, summary_text=summary_text)
        return await loop.run_in_executor(self._get_executor(), fn)


# Singleton instance
presidio_deidentification_service = PresidioDeIdentificationService()
