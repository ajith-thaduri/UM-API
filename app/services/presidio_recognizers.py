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
hospital_patterns = [
    Pattern(
        "Hospital",
        r"\b(?:[A-Z][a-z]+(?:'s?)?\s+){1,5}"
        r"(?:Hospital|Clinic|Medical Center|Health Center|Health System|"
        r"Medical Group|Diagnostic Laboratory|Recovery Center|Hospital Hospital)\b",
        0.95
    ),
    Pattern("Healthcare Org", r"\b[A-Z][a-z]+\s+Healthcare\b", 0.95),
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
VALID_STATES = r"AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MA|MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY"

location_patterns = [
    # City, State pairs
    Pattern("City StateAbbr", rf"\b[A-Z][a-z]+(?:\s[A-Z][a-z]+){{0,2}},\s*(?:{VALID_STATES})\b", 0.99),
    Pattern("City StateFull", r"\b[A-Z][a-z]+(?:\s[A-Z][a-z]+){{0,2}},\s*(?:Alabama|Alaska|Arizona|Arkansas|California|Colorado|Connecticut|Delaware|Florida|Georgia|Hawaii|Idaho|Illinois|Indiana|Iowa|Kansas|Kentucky|Louisiana|Maine|Maryland|Massachusetts|Michigan|Minnesota|Mississippi|Missouri|Montana|Nebraska|Nevada|New[ \t]Hampshire|New[ \t]Jersey|New[ \t]Mexico|New[ \t]York|North[ \t]Carolina|North[ \t]Dakota|Ohio|Oklahoma|Oregon|Pennsylvania|Rhode[ \t]Island|South[ \t]Carolina|South[ \t]Dakota|Tennessee|Texas|Utah|Vermont|Virginia|Washington|West[ \t]Virginia|Wisconsin|Wyoming)\b", 0.99),
    # Lone Cities (Commonly missed or ambiguous)
    Pattern("Major Cities", r"\b(?:Washington|Buffalo|Chicago|Austin|Seattle|Boston|Atlanta|Dallas|Denver|Houston|Miami|Phoenix|Philadelphia|Detroit|Minneapolis|Pittsburgh)\b", 0.85),
    # Locations like 'Shelter', 'Clinic'
    Pattern("Facility Word", r"\b(?:Homeless Shelter|Recovery Center|Nursing Home|Care Facility)\b", 0.85),
]

LocationRecognizer = PatternRecognizer(
    supported_entity="CITY_FACILITY",
    patterns=location_patterns,
    global_regex_flags=re.IGNORECASE | re.MULTILINE | re.DOTALL
)

# MAC Address Detection
mac_patterns = [
    Pattern("MAC Colon", r"\b([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}\b", 0.99),
    Pattern("MAC Dash", r"\b([0-9A-Fa-f]{2}-){5}[0-9A-Fa-f]{2}\b", 0.99),
]
MACAddressRecognizer = PatternRecognizer(
    supported_entity="MAC_ADDRESS",
    patterns=mac_patterns,
    name="MAC_Address_Recognizer"
)

# Sub-Address Detection (Apartment, Suite, Room, Unit)
sub_address_patterns = [
    Pattern("Apartment", r"\bAp(?:art)?(?:ment|t)\.?\s*#?\s*\w{1,6}\b", 0.99),
    Pattern("Suite", r"\bS(?:ui)?te\.?\s*#?\s*\w{1,6}\b", 0.99),
    Pattern("Room Number", r"\bR(?:oo)?m\.?\s*#?\s*\d{1,4}[A-Za-z]?\b", 0.85),
    Pattern("Floor", r"\bFl(?:oor)?\.?\s*#?\s*\d{1,3}[A-Za-z]?\b", 0.85),
    Pattern("Unit", r"\bUnit\s*#?\s*\w{1,6}\b", 0.95),
    Pattern("PO Box", r"\bP\.?\s*O\.?\s*Box\s+\d{1,6}\b", 0.99),
]
SubAddressRecognizer = PatternRecognizer(
    supported_entity="SUB_ADDRESS",
    patterns=sub_address_patterns,
    context=["Address", "Location", "Resides", "Lives", "mailing"],
    name="Sub_Address_Recognizer"
)

# HIPAA Category #1: DOB (excluding year)
dob_patterns = [
    Pattern("Month Day", r"\b(?:\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)|(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2})\b", 0.95),
]

DOBRecognizer = PatternRecognizer(
    supported_entity="DATE_TIME",
    patterns=dob_patterns
)

# Street Address
street_patterns = [
    # Full address with house number (optional ordinal)
    Pattern(
        "Street Address",
        r"\b\d{1,6}(?:st|nd|rd|th)?\s(?:[A-Za-z0-9#-]+\s){1,6}(?:Street|St|Avenue|Ave|Road|Rd|Blvd|Lane|Ln|Drive|Dr|Terrace|Way|Court|Ct|Circle|Cir|Place|Pl)\b",
        0.99
    ),
    # Bare street name (e.g. 'on 5th Street')
    Pattern(
        "Bare Street",
        r"\b(?:on|at|off|near)\s+(?:\d{1,3}(?:st|nd|rd|th)?\s+)?(?:[A-Za-z0-9]+\s+){1,2}(?:Street|St|Avenue|Ave|Road|Rd|Blvd|Lane|Ln|Drive|Dr|Place|Pl)\b",
        0.85
    )
]

StreetRecognizer = PatternRecognizer(
    supported_entity="STREET_ADDRESS",
    patterns=street_patterns,
    context=["Address", "Location", "Resides", "Living"],
    global_regex_flags=re.IGNORECASE | re.MULTILINE
)

# ZIP Code
zip_patterns = [
    Pattern("ZIP Code", r"\b\d{5}(?:-\d{4})?\b", 0.99)
]

ZipRecognizer = PatternRecognizer(
    supported_entity="ZIP_CODE",
    patterns=zip_patterns,
    context=["Zip", "Postal", "IL", "AZ", "NY", "CA", "TX"],
    global_regex_flags=re.IGNORECASE | re.MULTILINE
)

# Age Recognizer (Force match for redact check)
age_patterns = [
    Pattern("Age pattern", r"\b\d{1,3}\s*(?:year|yr)s?\s*old\b", 0.95),
    Pattern("Age value", r"\bAge:\s*\d{1,3}\b", 0.95),
]
AgeRecognizer = PatternRecognizer(
    supported_entity="AGE",
    patterns=age_patterns,
    context=["Age", "years", "old"]
)

# National Provider Identifier
npi_patterns = [
    Pattern("NPI", r"\bNPI[:\s]*\d{10}\b", 0.99)
]

NPIRecognizer = PatternRecognizer(
    supported_entity="NPI",
    patterns=npi_patterns,
    context=["Provider", "NPI"],
    global_regex_flags=re.IGNORECASE | re.MULTILINE
)

# Insurance Policy
insurance_patterns = [
    Pattern("Insurance Policy", r"\b[A-Z]{2,6}-[A-Z]{2,6}-\d{5,12}\b", 0.99)
]

InsuranceRecognizer = PatternRecognizer(
    supported_entity="INSURANCE_ID", 
    patterns=insurance_patterns,
    context=["Policy", "Group", "Insurance", "BCBS", "Aetna", "Cigna", "United"],
    global_regex_flags=re.IGNORECASE | re.MULTILINE
)

# IP Address
ip_patterns = [
    Pattern("IPv4", r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b", 0.99),
]
IPRecognizer = PatternRecognizer(
    supported_entity="IP_ADDRESS",
    patterns=ip_patterns,
    context=["IP", "Address", "Network"],
    name="IP_Address_Recognizer"
)

# Social Security Number
ssn_patterns = [
    Pattern("SSN", r"\b\d{3}-\d{2}-\d{4}\b", 0.99),
]
SSNRecognizer = PatternRecognizer(
    supported_entity="SSN",
    patterns=ssn_patterns,
    context=["SSN", "Social Security", "Tax ID"],
    name="SSN_Recognizer"
)

# Emergency Contact Name (Contextual)
emergency_patterns = [
    Pattern("Emergency Contact", r"\bEmergency\s+Contact[:\s]+([A-Z][a-z]+)\s+([A-Z][a-z]+)\b", 0.99),
    Pattern("Spouse", r"\bSpouse[:\s]+([A-Z][a-z]+)\s+([A-Z][a-z]+)\b", 0.9),
]
EmergencyContactRecognizer = PatternRecognizer(
    supported_entity="PERSON",
    patterns=emergency_patterns,
    context=["Emergency", "Spouse", "Contact", "Relationship"]
)

# Device ID / Account Number
account_patterns = [
    Pattern("ID Pattern", r"\b[A-Z]{2,4}-\d{6,15}\b", 0.95),
]
AccountRecognizer = PatternRecognizer(
    supported_entity="ID",
    patterns=account_patterns,
    context=["ID", "Account", "Device", "Passport", "License"]
)

# Vehicle Plate (HIPAA Category #15)
vehicle_patterns = [
    Pattern("Vehicle Plate", r"\b[A-Z]{2}-[A-Z]{2,4}-\d{4}\b", 0.95),
]
VehiclePlateRecognizer = PatternRecognizer(
    supported_entity="VEHICLE_PLATE",
    patterns=vehicle_patterns,
    context=["Plate", "Vehicle", "VIN", "License Plate"],
    name="Vehicle_Plate_Recognizer"
)

# Passport (HIPAA Category #16)
passport_patterns = [
    Pattern("Passport", r"\b[A-Z]\d{8,9}\b", 0.95),
]
PassportRecognizer = PatternRecognizer(
    supported_entity="PASSPORT",
    patterns=passport_patterns,
    context=["Passport", "Travel", "Nationality"],
    name="Passport_Recognizer"
)

# Driver's License (HIPAA Category #16)
license_patterns = [
    Pattern("Driver License", r"\b[A-Z]\d{6,8}\b", 0.95),
]
DriversLicenseRecognizer = PatternRecognizer(
    supported_entity="DRIVERS_LICENSE",
    patterns=license_patterns,
    context=["License", "DL", "Driver", "Identification"],
    name="Drivers_License_Recognizer"
)
