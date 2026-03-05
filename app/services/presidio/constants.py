"""
presidio/constants.py
━━━━━━━━━━━━━━━━━━━━
All static configuration for the Presidio de-identification service.

Centralises:
  - Entity type normalization / label maps
  - NER false-positive block-lists
  - Compiled regexes for NER quality checks
  - TOKENIZE / STRIP tiers
  - PHI field and free-text field lists
  - Model registry & entity priority map
"""

import re

# ── Transformer model label → Presidio entity mapping ────────────────────────
ROBERTA_LABEL_TO_PRESIDIO = {
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
    "IP": "PII",
    "URL": "PII",
    "OTHERPHI": "NRP",
}

# ── Entity type normalisation ─────────────────────────────────────────────────
ENTITY_TYPE_NORMALIZATION: dict = {
    # --- Person ---
    "PATIENT": "PERSON",
    "PATIENT_FULL_NAME": "PERSON",
    "PERSON": "PERSON",
    "PROVIDER": "PERSON",
    "DOCTOR": "PERSON",
    "STAFF": "PERSON",
    "HCW": "PERSON",
    "USER": "PERSON",
    "EMERGENCY_CONTACT": "PERSON",
    # --- Organisation ---
    "HOSPITAL": "ORGANIZATION",
    "HOSP": "ORGANIZATION",
    "FACILITY": "ORGANIZATION",
    "CLINIC": "ORGANIZATION",
    "PHARMACY": "ORGANIZATION",
    "VENDOR": "ORGANIZATION",
    "PATORG": "ORGANIZATION",
    "ORGANIZATION": "ORGANIZATION",
    # --- IDs ---
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
    # --- Location ---
    "STREET_ADDRESS": "LOCATION",
    "CITY": "LOCATION",
    "CITY_FACILITY": "LOCATION",
    "ZIP_CODE": "LOCATION",
    "LOCATION": "LOCATION",
    "ADDRESS": "LOCATION",
    # --- Communication/Internet ---
    "PHONE_NUMBER": "PHONE_NUMBER",
    "FAX": "PHONE_NUMBER",
    "EMAIL_ADDRESS": "EMAIL_ADDRESS",
    "IP_ADDRESS": "IP_ADDRESS",
    "URL": "URL",
    "WEBSITE": "URL",
    # --- Other ---
    "DATE_TIME": "DATE_TIME",
    "TIME": "TIME",
    "AGE": "AGE",
    "SEX": "AGE",
    "COORDINATE": "COORDINATE",
}


def normalize_entity_type(entity_type: str) -> str:
    """Normalise entity type to standard Presidio category.
    Example: PATIENT_FULL_NAME → PERSON, HOSPITAL → ORGANIZATION
    """
    return ENTITY_TYPE_NORMALIZATION.get(entity_type, entity_type)


# ── NER False-Positive Block-lists ────────────────────────────────────────────
NER_EXACT_BLOCKLIST: set = {
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
    "insurance information", "billing information", "contact information",
    "financial information", "biometric identifiers", "medical identifiers",
    "vehicle information", "online references", "personal website", "notes",
    "gender", "male", "female", "office address", "hospital address",
    "hospital name", "attending physician", "referring physician",
    "primary nurse", "appointment time", "emergency contact",
    "health insurance", "insurance provider", "employee id",
    "laboratory accession", "radiology report", "encounter id",
    "prescription number", "patient portal", "login ip", "device id",
    "vehicle vin", "parking permit", "linkedin profile",
    "credit card", "bank account", "routing number", "billing account",
    "email address", "work email", "phone number", "alternate phone",
    "fax number", "driver license", "passport number",
    "pacemaker model", "serial number", "model number",
}

NER_PHRASE_BLOCKLIST: set = {
    "medical encounter", "encounter information", "patient demographics",
    "hospital encounter", "information hospital", "encounter details",
    "medical encounter details", "details hospital",
    "parkinson", "parkinson's", "crohn", "crohn's", "raynaud", "raynaud's",
    "alzheimer", "alzheimer's", "huntington", "huntington's", "glasgow coma",
    "glasgow", "medtronic", "azure", "medicare",
}

# ── Compiled regexes used by NER sanitizer ────────────────────────────────────
_PHONE_REGEX = re.compile(
    r'^(?:\+?1[-. ]?)?\(?\d{3}\)?[-. ]?\d{3}[-. ]?\d{4}$'
)
_STREET_REGEX = re.compile(
    r'^\d{1,6}(?:st|nd|rd|th)?\s+(?:[A-Za-z0-9]+\s+){0,5}'
    r'(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|'
    r'Drive|Dr|Terrace|Way|Court|Ct|Circle|Cir|Place|Pl|'
    r'Highway|Hwy|Parkway|Pkwy)\b',
    re.IGNORECASE
)
_CLINICAL_CONTEXT_WORDS: set = {
    "under", "care", "patient", "admitted", "discharged",
    "presented", "history", "physician", "services"
}
_MAX_ENTITY_SPAN = 50
_MIN_ENTITY_CHARS = 3
_SUFFIX_ONLY_REGEX = re.compile(
    r'^[,()\s]*\b(?:MD|DO|PhD|NP|PA|RN|LPN|FNP|DNP|JD|MSW|LCSW|FACS|FACC|FCCP)\b[.,()\s]*$',
    re.IGNORECASE
)
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
_MAX_SPAN_BY_TYPE: dict = {
    "PERSON": 40,
    "ORGANIZATION": 60,
    "LOCATION": 50,
}
_DEFAULT_MAX_SPAN = 60

# ── Clinical Relevance Tiers ──────────────────────────────────────────────────
# Entity types that get numbered tokens (AI needs to distinguish these)
TOKENIZE_TYPES: set = {"PERSON", "ORGANIZATION"}

# Entity types stripped to [[REDACTED]] (zero clinical value for summary)
STRIP_TYPES: set = {
    "ID", "PHONE_NUMBER", "EMAIL_ADDRESS", "US_SSN", "SSN",
    "LOCATION", "IP_ADDRESS", "URL", "PII", "ADDRESS",
    "INSURANCE_ID", "NPI", "MRN", "PASSPORT",
    "DRIVERS_LICENSE", "DEVICE_ID", "VEHICLE_PLATE",
    "ACCOUNT_NUMBER", "FAX", "NATIONAL_ID", "WEBSITE",
    "ZIP_CODE", "STREET_ADDRESS", "CITY", "MAC_ADDRESS", "SUB_ADDRESS",
    "COORDINATE", "TIME", "USERNAME", "FILENAME",
}

# ── Field name lists ──────────────────────────────────────────────────────────
# Known structured PHI field names (used for structured-first replacement)
KNOWN_PHI_FIELDS: set = {
    "patient_name", "patient_first_name", "patient_last_name",
    "mrn", "medical_record_number", "case_number",
    "facility", "facility_name", "hospital",
    "provider", "provider_name", "physician", "doctor", "referring_physician",
}

# Structured data fields that contain free narrative text (requires Presidio scanning)
FREE_TEXT_FIELDS: set = {
    "description", "narrative", "note", "comment",
    "details", "content", "text", "summary",
}

# Date-field keyword detection
DATE_FIELD_KEYWORDS: set = {
    "date", "time", "timestamp", "occurred",
    "started", "ended", "admitted", "discharged",
}

# ── NER model registry ────────────────────────────────────────────────────────
NER_MODEL_REGISTRY: dict = {
    "spacy": {
        "label": "spaCy (en_core_web_lg)",
        "description": "General-purpose NER, fast, good baseline",
        "engine": "spacy",
        "model": "en_core_web_lg",
    },
    "transformers": {
        "label": "RoBERTa Medical (obi/deid_roberta_i2b2)",
        "description": "Medical de-identification model trained on i2b2. Best for clinical PHI.",
        "engine": "transformers",
        "model": "obi/deid_roberta_i2b2",
    },
}

# ── Entity priority (higher = wins in tie-breaks) ─────────────────────────────
ENTITY_PRIORITY: dict = {
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
