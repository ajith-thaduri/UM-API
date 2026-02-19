import re
from presidio_analyzer import PatternRecognizer, Pattern

# HIPAA Category #8: Medical Record Numbers
mrn_patterns = [
    Pattern("MRN with prefix", r"\bMRN[:\s]*\d{4,12}\b", 0.95),
]

MRNRecognizer = PatternRecognizer(
    supported_entity="MRN",
    patterns=mrn_patterns
)

# HIPAA Element: Time 
time_patterns = [
    Pattern("12h Time", r"\b\d{1,2}:\d{2}\s?(?:AM|PM|am|pm)\b", 0.95),
    Pattern("24h Time", r"\b(?:[01]\d|2[0-3]):[0-5]\d\b", 0.85),
    Pattern("Time with context", r"\b(?:at|@)\s*\d{1,2}:\d{2}\b", 0.8),
]

TimeRecognizer = PatternRecognizer(
    supported_entity="TIME",
    patterns=time_patterns
)

# HIPAA Category #4: Names of healthcare providers or facilities
# Strictly match Proper Noun + Hospital. Case sensitive to avoid sentence capture.
hospital_patterns = [
    Pattern("Hospital", r"\b[A-Z][A-Za-z\s]{3,50}(?:Hospital|Clinic|Medical Center)\b", 0.95), 
    Pattern("Healthcare", r"\b[A-Z][a-z]+\sHealthcare\b", 0.95),
]

HospitalRecognizer = PatternRecognizer(
    supported_entity="HOSPITAL",
    patterns=hospital_patterns,
    global_regex_flags=re.MULTILINE | re.DOTALL 
)

# HIPAA Category #1: Names (Doctors/Providers)
doctor_patterns = [
    Pattern("Dr. Name", r"\b(?:Dr\.?|Doctor|Physician)\s+[A-Z][a-z]+\s+[A-Z][a-z]+\b", 0.95),
    Pattern("Dr. Single Name", r"\b(?:Dr\.?|Doctor|Physician)\s+[A-Z][a-z]+\b", 0.9),
]

DoctorRecognizer = PatternRecognizer(
    supported_entity="PROVIDER",
    patterns=doctor_patterns,
    global_regex_flags=re.MULTILINE | re.DOTALL
)

# HIPAA Category #1: Full Patient Names
name_patterns = [
    Pattern("Labeled Patient Name", r"\b(?:Patient|Name|PT)[:\s]+([A-Z][a-z]+)\s+([A-Z][a-z]+)\b", 0.95),
    Pattern("Name with Salutation", r"\b(?:Mr\.|Ms\.|Mrs\.|Miss)\s+([A-Z][a-z]+)\s+([A-Z][a-z]+)\b", 0.95),
    Pattern("Contextual Full Name", r"\b([A-Z][a-z]+)\s([A-Z][a-z]+)\b", 0.85) 
]

FullNameRecognizer = PatternRecognizer(
    supported_entity="PATIENT_FULL_NAME",
    patterns=name_patterns,
    context=["Patient", "Name", "Mr.", "Mrs.", "Miss", "Ms."],
    global_regex_flags=re.MULTILINE | re.DOTALL
)

# HIPAA Category #2: Geographic subdivisions
VALID_STATES = "AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MA|MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY"

city_patterns = [
    Pattern("City", r"\bHyderabad\b", 0.95),
    # Strict City, State pattern
    Pattern("City State", rf"\b[A-Z][a-z]+,\s*(?:{VALID_STATES})\b", 0.95),
]

CityRecognizer = PatternRecognizer(
    supported_entity="CITY",
    patterns=city_patterns,
    global_regex_flags=re.MULTILINE | re.DOTALL
)

# HIPAA Category #1: DOB (excluding year)
dob_patterns = [
    Pattern("Month Day", r"\b(?:\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)|(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2})\b", 0.95),
]

DOBRecognizer = PatternRecognizer(
    supported_entity="DATE_TIME",
    patterns=dob_patterns
)

# HIPAA Category #2: Street Address
# UPDATED: Use user-provided regex exactly and IGNORECASE w/ higher score
street_patterns = [
    Pattern(
        "Street Address",
        r"\b\d{1,6}\s(?:[A-Za-z0-9]+\s){1,6}(?:Street|St|Avenue|Ave|Road|Rd|Blvd|Lane|Ln|Drive|Dr|Terrace|Way|Court|Ct)\b",
        0.99
    )
]

StreetRecognizer = PatternRecognizer(
    supported_entity="STREET_ADDRESS",
    patterns=street_patterns,
    context=["Address", "Location", "Resides", "Living"],
    global_regex_flags=re.IGNORECASE | re.MULTILINE
)

# HIPAA Category #2: ZIP Code
# UPDATED: Higher Score
zip_patterns = [
    Pattern(
        "ZIP Code",
        r"\b\d{5}(?:-\d{4})?\b",
        0.99
    )
]

ZipRecognizer = PatternRecognizer(
    supported_entity="ZIP_CODE",
    patterns=zip_patterns,
    context=["Zip", "Postal", "IL", "AZ", "NY", "CA", "TX"],
    global_regex_flags=re.IGNORECASE | re.MULTILINE
)

# HIPAA Category #8: National Provider Identifier
# UPDATED: Higher Score
npi_patterns = [
    Pattern(
        "NPI",
        r"\bNPI[:\s]*\d{10}\b",
        0.99
    )
]

NPIRecognizer = PatternRecognizer(
    supported_entity="NPI",
    patterns=npi_patterns,
    context=["Provider", "NPI"],
    global_regex_flags=re.IGNORECASE | re.MULTILINE
)

# HIPAA Category #? Insurance Policy
insurance_patterns = [
    Pattern(
        "Insurance Policy",
        r"\b[A-Z]{2,6}-[A-Z]{2,6}-\d{5,12}\b",
        0.95
    )
]

InsuranceRecognizer = PatternRecognizer(
    supported_entity="INSURANCE_ID", 
    patterns=insurance_patterns,
    context=["Policy", "Group", "Insurance", "BCBS", "Aetna", "Cigna", "United"],
    global_regex_flags=re.IGNORECASE | re.MULTILINE
)
