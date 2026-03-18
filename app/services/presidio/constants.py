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


# ── Clinical Content Protection ──────────────────────────────────────────────
# Single clinical words. If a detected PERSON/ORG span contains any of these,
# it is clinical content, not PHI, and must not be redacted.
MEDICAL_WORD_SET: set = {
    # Diseases
    "diabetes", "mellitus", "hypertension", "failure", "syndrome", "disease",
    "disorder", "infection", "cancer", "tumor", "carcinoma", "lymphoma",
    "neuropathy", "retinopathy", "nephropathy", "osteoarthritis", "obesity",
    "asthma", "arthritic", "copd", "emphysema", "bronchitis", "md",
    # Vitals / Labs
    "vitals", "pressure", "saturation", "rate", "count", "panel", "analysis",
    "culture", "function", "glucose", "cholesterol", "creatinine", "albumin",
    "hemoglobin", "platelet", "sodium", "potassium", "sedimentation",
    "bilirubin", "triglycerides", "ferritin", "urea", "lipid", "metabolic",
    "inflammatory", "labs", "laboratory", "specimen", "sample",
    # Medications (common)
    "medications", "medicine", "medication", "acetaminophen", "metformin", "albuterol",
    "theophylline", "fluticasone", "lisinopril", "atorvastatin", "aspirin",
    "insulin", "warfarin", "amoxicillin", "ibuprofen", "omeprazole",
    "vaccination", "influenza", "dosage", "refill", "refills", "mg", "ml",
    # Anatomy / procedures
    "pulmonary", "respiratory", "arterial", "venous", "cardiac", "renal",
    "hepatic", "thyroid", "peripheral", "conduction", "surgery", "imaging",
    "radiology", "pathology", "consultation", "assessment", "evaluation",
}


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
    "primary nurse", "appointment time",
    "health insurance", "insurance provider", "employee id",
    "laboratory accession", "radiology report", "encounter id",
    "prescription number", "login ip", "device id",
    "vehicle vin", "linkedin profile",
    "credit card", "bank account", "routing number", "billing account",
    "email address", "work email", "phone number", "alternate phone",
    "fax number", "driver license", "passport number",
    "pacemaker model", "serial number", "model number",
    # Comprehensive Edge Cases — general labels
    "alias name", "beneficiary number", "browser fingerprint",
    "biometric authentication", "primary vehicle", "vehicle owner",
    "vehicle make", "vehicle model", "vehicle year", "vehicle color",
    "license plate", "vehicle identification", "parking permit",
    "card number", "expiration date", "billing address", "visit date",
    "room number", "bed number", "face scan", "lab order", "test date",
    "sample id", "laboratory facility", "claim number", "group id",
    # Address / location labels
    "home address", "secondary address", "third address", "mailing address",
    "hospital address", "office address", "billing address", "street address",
    "zip code", "county", "state", "country",
    # Device / network labels
    "mac address", "mac alt format", "alt format", "ip address",
    "ipv6", "device id", "browser fingerprint id", "face scan id",
    "biometric token", "biometric authentication token",
    # Vehicle / ID labels and parking
    "vin", "plate", "parking", "parking permit id",
    "vehicle identification number",
    # Payment labels
    "card holder", "credit card holder", "card number",
    "expiration date", "cvv", "billing address",
    # Lab / test labels
    "lab order id", "sample id", "test date", "laboratory facility",
    # Insurance / claim labels
    "policy number", "claim number", "health plan", "group id",
    "insurance claim information", "insurance provider",
    # Miscellaneous
    "discharge instructions", "follow-up", "primary vehicle",
    "additional vehicle", "additional pii edge cases",
    "repeated phi stress section", "chief complaint",
    "physical examination", "allergies",
    "social history", "case metadata",
    "address information", "previous address", "temporary residence", "patient home",
    "fax numbers", "email addresses", "personal email", "corporate email", "portal email",
    "record number", "radiology study", "clinical trial",
    "financial identifiers", "plan beneficiary", "insurance policy", "insurance claim",
    "identification documents", "vehicle registration", "internet identifiers", "mobile device",
    "patient portals", "insurance portal", "telehealth session",
    "prescription portal", "retina scan", "face recognition", "voice recognition",
    "patient photograph", "image file", "dates related", "surgery date",
    "employer information", "parking garage", "nurse name",
    "doctor information",
    "doctor notes", "doctor notes past", "exercise habits", "eye exam", "fatty acids",
    "follow up",
    "initial osteoarthritis", "last done",
    "lifestyle data", "lifestyle information", "medical conditions",
    "medical data", "medical sections", "medical terms", "medical tests",
    "new concerns", "new or", "occasionally diet",
    "patient lifestyle", "patient summary",
    "routine check",
    "section headings", "smoking status", "status on",
    "subjective observations", "table of", "tesla model", "midnight silver", "patient account number",
    "device identifier", "website mentioned", "location information", "during treatment",
    "encounter timeline", "admission time", "initial emergency", "department evaluation",
    "radiology imaging", "cardiology consultation", "procedure date", "staff information",
    "consulting cardiologist", "nurse supervisor", "payment authorization",
    "billing reference", "diagnostic identifiers", "radiology image",
    "scan file", "pathology report", "implant identifiers", "cardiac implant",
    "device serial", "device tracking", "digital identifiers", "electronic prescription",
    "patient monitoring device", "additional narrative",
    "recorded date", "doctor name", "doctor unique", "doctor information doctor",
    "past hospital", "doctor notes past", "date of", "coordinator for", "encounter summary",
    "start service", "encounter participant", "appointment confirmation", "confirmed on",
    "paitnet summary", "visit current", "visits date",
    "document / section text", "diagnostic form",
    "electronically signed", "insurance agent", "state id", "employer employee id",
    "patient profile photo file name", "east wing", "industrial parkway", "number used",
    "employer information employer", "accession number", "network identifiers",
    "vehicle license", "is his wife", "employee id at the company", "login session",
    "his social", "security number", "his bank", "her social", "her bank",
    "is her husband", "the pharmacy", "with group", "details were provided",
    "biometric identifier", "vehicle number", "patient photo", "patient information",
    "phone numbers", "company name", "commerce plaza", "insurance contact", "heart rate",
    "blood sample", "scan technician", "facial recognition", "patient medical record",
    "admission details", "clinical notes", "device information", "license number",
    "biometric information", "web information", "location data", "family members",
    "primary care", "alias used in prior records", "jane doe at", "employer id", "vehicle plate",
    # --- New blocked terms ---
    "doctor notes subjective","Doctor Notes Subjective","Doctor Information Doctor",
    "doctor notes michael", "doctor notes robert",
    "doctor notes phyllis",
    "dosage frequency", "twice daily", "once daily",
    "general wellness",
    "employer employee",
}

NER_PHRASE_BLOCKLIST: set = {
    "medical encounter", "encounter information", "patient demographics",
    "hospital encounter", "information hospital", "encounter details",
    "medical encounter details", "details hospital",
    "parkinson", "parkinson's", "crohn", "crohn's", "raynaud", "raynaud's",
    "alzheimer", "alzheimer's", "huntington", "huntington's", "glasgow coma",
    "glasgow", "medtronic", "azure", "medicare",
    "county", "patient portal", "employer name", "biometric authentication token",
    "discharge instructions", "midwest diagnostic", "senior software engineer",
    "senior software", "alt format", "mac alt",
    "diet", "symptoms", "vaccination",
    "tesla", "midnight silver",
}

# ── Field-label stop-words (Rule 11 in sanitizer) ─────────────────────────────
# Words that are NEVER parts of real human names — if PERSON text is composed
# ENTIRELY of these words, drop it.
FIELD_LABEL_STOP_WORDS: set = {
    "address", "account", "alt", "authentication", "biometric", "billing",
    "browser", "card", "claim", "color", "contact", "country", "county",
    "credit", "cvv", "date", "device", "discharge", "driver", "email",
    "emergency", "employer", "expiration", "facility", "fax", "fingerprint",
    "floor", "format", "group", "health", "holder", "home", "hospital",
    "id", "identification", "information", "insurance", "ip", "lab",
    "laboratory", "license", "mac", "make", "medical", "mobile",
    "model", "name", "network", "number", "order", "owner", "parking",
    "passport", "patient", "payment", "permit", "phone", "plan",
    "plate", "policy", "portal", "primary", "record", "room",
    "sample", "scan", "secondary", "security", "social", "state",
    "suite", "summary", "test", "third", "token", "unit", "url",
    "username", "vehicle", "vin", "visit", "year", "zip",
    "additional", "alt", "bed", "beneficiary", "chief",
    "complaint", "edge", "examination", "follow-up", "history",
    "instructions", "notes", "physical", "pii",
    "repeated", "section", "stress", "type",
    "residence", "home", "portal", "session", "recognition", "photograph",
    "image", "related", "garage", "status", "silver", "tesla",
    "supervisor", "technician", "authorization",
    "reference", "serial", "tracking", "digital",
    "electronic", "monitoring", "narrative", "treatment", "encounter",
    "timeline", "evaluation", "procedure", "trial",
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
