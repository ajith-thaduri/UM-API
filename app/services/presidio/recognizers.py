import re
from presidio_analyzer import PatternRecognizer, Pattern

# HIPAA Category #8: Medical Record Numbers
mrn_patterns = [
    Pattern("MRN with prefix", r"\bMRN[:\s]*\d{4,12}\b", 0.95),
]

MRNRecognizer = PatternRecognizer(
    supported_entity="MRN",
    patterns=mrn_patterns,
    name="MRN_Recognizer"
)

# HIPAA Element: Time 
time_patterns = [
    Pattern("12h Time", r"\b\d{1,2}:\d{2}\s?(?:AM|PM|am|pm)\b", 0.95),
    Pattern("24h Time", r"\b(?:[01]\d|2[0-3]):[0-5]\d\b", 0.85),
    Pattern("Time with context", r"\b(?:at|@)\s*\d{1,2}:\d{2}\b", 0.85),
]

TimeRecognizer = PatternRecognizer(
    supported_entity="TIME",
    patterns=time_patterns,
    name="Time_Recognizer"
)

# HIPAA Category #4: Names of healthcare providers or facilities
hospital_patterns = [
    Pattern(
        "Hospital",
        r"\b(?:[A-Z][a-z.]+(?:['’\u2018\u2019]s?)?[ \t]+){1,5}"
        r"(?:Hospital|Clinic|Medical Center|Health Center|Health System|"
        r"Medical Group|Diagnostic Laboratory|Recovery Center|Pharmacy)\b",
        0.95
    ),
    Pattern("Healthcare Org", r"\b[A-Z][a-z]+\s+Healthcare\b", 0.95),
]

HospitalRecognizer = PatternRecognizer(
    supported_entity="HOSPITAL",
    patterns=hospital_patterns,
    global_regex_flags=re.MULTILINE | re.DOTALL,
    name="Hospital_Recognizer"
)

# Employers / Organizations
employer_patterns = [
    Pattern("Labeled Employer", r"\bEmployer[:\s]+([A-Z][a-z]+(?:\s+[A-Z][A-Za-z]+){0,3})\b", 0.95),
    Pattern("Corporate Org", r"\b(?:[A-Z][A-Za-z.'-]+(?:[ \t]+[A-Z][A-Za-z.'-]+){0,3})[ \t]+(?:Corporation|Corp\.|Inc\.|LLC|Company|Logistics|Power[ \t]+Plant|Bank|Pharmacy|Group)\b", 0.95),
    Pattern("BlueCross", r"\bBlue[ \t]?Cross[ \t]?(?:Blue[ \t]?Shield)?(?:[ \t]+of[ \t]+[A-Z][A-Za-z]+)?\b", 0.95)
]
EmployerRecognizer = PatternRecognizer(
    supported_entity="ORGANIZATION",
    patterns=employer_patterns,
    context=["Employer", "Company"],
    global_regex_flags=re.IGNORECASE | re.MULTILINE,
    name="Employer_Recognizer"
)

# HIPAA Category #1: Names (Doctors/Providers)
doctor_patterns = [
    Pattern("Dr. Name", r"\b(?:Dr\.?|Doctor|Physician)\s+(?!Phone\b|Email\b|Contact\b|Fax\b|Signature\b)[A-Z][a-z]+\s+[A-Z][a-z]+\b", 0.95),
    Pattern("Dr. Single Name", r"\b(?:Dr\.?|Doctor|Physician)\s+(?!Phone\b|Email\b|Contact\b|Fax\b|Signature\b)[A-Z][a-z]+\b", 0.9),
]

DoctorRecognizer = PatternRecognizer(
    supported_entity="PROVIDER",
    patterns=doctor_patterns,
    global_regex_flags=re.MULTILINE,
    name="Doctor_Recognizer"
)

# HIPAA Category #1: Full Patient Names
name_patterns = [
    Pattern("Labeled Patient Name", r"\b(?:Patient(?:\s+Name)?|Name|PT)[:\s]+([A-Z][a-z]+(?:[\s-][A-Z][a-z]+){1,3})\b", 0.95),
    Pattern("Alias Label", r"\b(?:Alias|AKA|Also known as|Goes by)[:\s]+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\b", 0.95),
    Pattern("Emergency Contact", r"\b(?:Emergency\s+Contact|Spouse|Relative)[:\s\n]+(?:Name[:\s]+)?([A-Z][a-z]+(?:[\s-][A-Z][a-z]+){1,2})\b", 0.95),
    Pattern("Name with Salutation", r"\b(?:Mr\.|Ms\.|Mrs\.|Miss)\s+([A-Z][a-z]+)\s+([A-Z][a-z]+)\b", 0.95),
    Pattern("Contextual Full Name", r"\b(?!(?:Medical|Center|Hospital|Clinic|Health|Pharmacy|Group|System|Laboratory)\b)([A-Z][a-z]+)\s(?!(?:Medical|Center|Hospital|Clinic|Health|Pharmacy|Group|System|Laboratory)\b)([A-Z][a-z]+)\b", 0.85) 
]

FullNameRecognizer = PatternRecognizer(
    supported_entity="PATIENT_FULL_NAME",
    patterns=name_patterns,
    context=["Patient", "Name", "Mr.", "Mrs.", "Miss", "Ms.", "Alias", "Contact", "Spouse", "Dan", "Mitchell"],
    global_regex_flags=re.MULTILINE,
    name="FullName_Recognizer"
)

# HIPAA Category #2: Geographic subdivisions
VALID_STATES = r"AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|MA|MD|ME|MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY"

location_patterns = [
    # City, State pairs (same line — with comma separation)
    Pattern("City StateAbbr", rf"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){{0,2}},\s*(?:{VALID_STATES})\b", 0.99),
    Pattern("City StateFull", r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){{0,2}},\s*(?:Alabama|Alaska|Arizona|Arkansas|California|Colorado|Connecticut|Delaware|Florida|Georgia|Hawaii|Idaho|Illinois|Indiana|Iowa|Kansas|Kentucky|Louisiana|Maine|Maryland|Massachusetts|Michigan|Minnesota|Mississippi|Missouri|Montana|Nebraska|Nevada|New[ \t]Hampshire|New[ \t]Jersey|New[ \t]Mexico|New[ \t]York|North[ \t]Carolina|North[ \t]Dakota|Ohio|Oklahoma|Oregon|Pennsylvania|Rhode[ \t]Island|South[ \t]Carolina|South[ \t]Dakota|Tennessee|Texas|Utah|Vermont|Virginia|Washington|West[ \t]Virginia|Wisconsin|Wyoming)\b", 0.99),
    # Lone states (Standalone State Words)
    Pattern("State Full", r"\b(?:Alabama|Alaska|Arizona|Arkansas|California|Colorado|Connecticut|Delaware|Florida|Georgia|Hawaii|Idaho|Illinois|Indiana|Iowa|Kansas|Kentucky|Louisiana|Maine|Maryland|Massachusetts|Michigan|Minnesota|Mississippi|Missouri|Montana|Nebraska|Nevada|New[ \t]Hampshire|New[ \t]Jersey|New[ \t]Mexico|New[ \t]York|North[ \t]Carolina|North[ \t]Dakota|Ohio|Oklahoma|Oregon|Pennsylvania|Rhode[ \t]Island|South[ \t]Carolina|South[ \t]Dakota|Tennessee|Texas|Utah|Vermont|Virginia|Washington|West[ \t]Virginia|Wisconsin|Wyoming)\b", 0.90),
    # Lone Cities — extended with more common US cities
    Pattern("Major Cities", r"\b(?:Washington|Buffalo|Chicago|Austin|Seattle|Boston|Atlanta|Dallas|Denver|Houston|Miami|Phoenix|Philadelphia|Detroit|Minneapolis|Pittsburgh|San Diego|San Francisco|San Jose|San Antonio|Los Angeles|New York|Las Vegas|Portland|Sacramento|Springfield|Jacksonville|Memphis|Nashville|Louisville|Baltimore|Milwaukee|Albuquerque|Tucson|Fresno|Mesa|Omaha|Raleigh|Cleveland|Arlington|Tampa|New Orleans|Bakersfield|Honolulu|Anaheim|Aurora|Santa Ana|Corpus Christi|Riverside|Lexington|Stockton|Henderson|Saint Paul|Cincinnati|Greensboro|Pittsburgh|St\. Louis|Lincoln|Orlando|Irvine|Durham|Madison|Fort Worth|El Paso|Columbus|Charlotte|Indianapolis)\b", 0.90),
    # Locations like 'Shelter', 'Clinic'
    Pattern("Facility Word", r"\b(?:Homeless Shelter|Recovery Center|Nursing Home|Care Facility)\b", 0.85),
]

LocationRecognizer = PatternRecognizer(
    supported_entity="CITY_FACILITY",
    patterns=location_patterns,
    global_regex_flags=re.IGNORECASE | re.MULTILINE | re.DOTALL,
    name="Location_Recognizer"
)

state_patterns = [
    Pattern("State Full Labeled", r"\bState[:\s]+((?:Alabama|Alaska|Arizona|Arkansas|California|Colorado|Connecticut|Delaware|Florida|Georgia|Hawaii|Idaho|Illinois|Indiana|Iowa|Kansas|Kentucky|Louisiana|Maine|Maryland|Massachusetts|Michigan|Minnesota|Mississippi|Missouri|Montana|Nebraska|Nevada|New[ \t]Hampshire|New[ \t]Jersey|New[ \t]Mexico|New[ \t]York|North[ \t]Carolina|North[ \t]Dakota|Ohio|Oklahoma|Oregon|Pennsylvania|Rhode[ \t]Island|South[ \t]Carolina|South[ \t]Dakota|Tennessee|Texas|Utah|Vermont|Virginia|Washington|West[ \t]Virginia|Wisconsin|Wyoming))\b", 0.99),
    Pattern("State Abbr Labeled", r"\bState[:\s]+(AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY)\b", 0.99),
    Pattern("State Full", r"\b(?:Alabama|Alaska|Arizona|Arkansas|California|Colorado|Connecticut|Delaware|Florida|Georgia|Hawaii|Idaho|Illinois|Indiana|Iowa|Kansas|Kentucky|Louisiana|Maine|Maryland|Massachusetts|Michigan|Minnesota|Mississippi|Missouri|Montana|Nebraska|Nevada|New[ \t]Hampshire|New[ \t]Jersey|New[ \t]Mexico|New[ \t]York|North[ \t]Carolina|North[ \t]Dakota|Ohio|Oklahoma|Oregon|Pennsylvania|Rhode[ \t]Island|South[ \t]Carolina|South[ \t]Dakota|Tennessee|Texas|Utah|Vermont|Virginia|Washington|West[ \t]Virginia|Wisconsin|Wyoming)\b", 0.8),
]
StateRecognizer = PatternRecognizer(
    supported_entity="LOCATION",
    patterns=state_patterns,
    name="State_Recognizer"
)

country_patterns = [
    Pattern("Labeled Country", r"\bCountry[:\s]+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})\b", 0.99),
    Pattern("Country", r"\b(?:USA|U\.S\.|U\.S\.A\.|United States(?:\s+of\s+America)?|United Kingdom|UK|Canada|Mexico|Afghanistan|Albania|Algeria|Andorra|Angola|Antigua and Barbuda|Argentina|Armenia|Australia|Austria|Azerbaijan|Bahamas|Bahrain|Bangladesh|Barbados|Belarus|Belgium|Belize|Benin|Bhutan|Bolivia|Bosnia and Herzegovina|Botswana|Brazil|Brunei|Bulgaria|Burkina Faso|Burundi|Côte d'Ivoire|Cabo Verde|Cambodia|Cameroon|Canada|Central African Republic|Chad|Chile|China|Colombia|Comoros|Congo|Costa Rica|Croatia|Cuba|Cyprus|Czechia|Democratic Republic of the Congo|Denmark|Djibouti|Dominica|Dominican Republic|Ecuador|Egypt|El Salvador|Equatorial Guinea|Eritrea|Estonia|Eswatini|Ethiopia|Fiji|Finland|France|Gabon|Gambia|Georgia|Germany|Ghana|Greece|Grenada|Guatemala|Guinea|Guinea-Bissau|Guyana|Haiti|Holy See|Honduras|Hungary|Iceland|India|Indonesia|Iran|Iraq|Ireland|Israel|Italy|Jamaica|Japan|Jordan|Kazakhstan|Kenya|Kiribati|Kuwait|Kyrgyzstan|Laos|Latvia|Lebanon|Lesotho|Liberia|Libya|Liechtenstein|Lithuania|Luxembourg|Madagascar|Malawi|Malaysia|Maldives|Mali|Malta|Marshall Islands|Mauritania|Mauritius|Mexico|Micronesia|Moldova|Monaco|Mongolia|Montenegro|Morocco|Mozambique|Myanmar|Namibia|Nauru|Nepal|Netherlands|New Zealand|Nicaragua|Niger|Nigeria|North Korea|North Macedonia|Norway|Oman|Pakistan|Palau|Palestine State|Panama|Papua New Guinea|Paraguay|Peru|Philippines|Poland|Portugal|Qatar|Romania|Russia|Rwanda|Saint Kitts and Nevis|Saint Lucia|Saint Vincent and the Grenadines|Samoa|San Marino|Sao Tome and Principe|Saudi Arabia|Senegal|Serbia|Seychelles|Sierra Leone|Singapore|Slovakia|Slovenia|Solomon Islands|Somalia|South Africa|South Korea|South Sudan|Spain|Sri Lanka|Sudan|Suriname|Sweden|Switzerland|Syria|Tajikistan|Tanzania|Thailand|Timor-Leste|Togo|Tonga|Trinidad and Tobago|Tunisia|Turkey|Turkmenistan|Tuvalu|Uganda|Ukraine|United Arab Emirates|United Kingdom|United States of America|Uruguay|Uzbekistan|Vanuatu|Venezuela|Vietnam|Yemen|Zambia|Zimbabwe)\b", 0.85),
]
CountryRecognizer = PatternRecognizer(
    supported_entity="LOCATION",
    patterns=country_patterns,
    name="Country_Recognizer"
)

# County Detection
county_patterns = [
    Pattern("County Labeled", r"\bCounty[:\s]+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}\s+County)\b", 0.99),
    Pattern("County Name", r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})\s+County\b", 0.95),
]
CountyRecognizer = PatternRecognizer(
    supported_entity="LOCATION",
    patterns=county_patterns,
    context=["county", "region", "district"],
    name="County_Recognizer"
)

# URL Detection
url_patterns = [
    Pattern("Labeled URL", r"\b(?:URL|Website|Web|Link|Patient\s+Portal)[:\s]+((?:https?://|www[:.]?)[a-zA-Z0-9-]+\.[a-zA-Z0-9.-]+(?:/[a-zA-Z0-9._?=&%/#~+-]*)?)\b", 0.99),
    Pattern("Labeled Naked Domain", r"\b(?:URL|Website|Web|Link|Patient\s+Portal)[:\s]+([a-zA-Z0-9-]+\.(?:com|org|net|edu|gov|io|co|us|me)(?:/[a-zA-Z0-9._?=&%/#~+-]*)?)\b", 0.99),
    Pattern("Standard Protocol URL", r"\b(?:https?://|www[:.]?)[a-zA-Z0-9-]+\.[a-zA-Z0-9.-]+(?:/[a-zA-Z0-9._?=&%/#~+-]*)?\b", 0.95),
]
UrlRecognizer = PatternRecognizer(
    supported_entity="URL",
    patterns=url_patterns,
    context=["http", "https", "www", "url", "portal", "website", "link"],
    name="URL_Recognizer"
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
    Pattern("Apartment", r"\b(?:Apt\.?|Apartment)\b\s*#?\s*[A-Za-z0-9]{1,6}\b", 0.99),
    Pattern("Suite", r"\b(?:Suite|Ste\.?)\b\s*#?\s*[A-Za-z0-9]{1,6}\b", 0.99),
    Pattern("Room Number", r"\b(?:Room|Rm\.?)\b\s*#?\s*\d{1,4}[A-Za-z]?\b", 0.85),
    Pattern("Floor", r"\b(?:Floor|Fl\.?)\b\s*#?\s*\d{1,3}[A-Za-z]?\b", 0.85),
    Pattern("Unit", r"\bUnit\b\s*#?\s*[A-Za-z0-9]{1,6}\b", 0.95),
    Pattern("PO Box", r"\bP\.?\s*O\.?\s*Box\b\s+\d{1,6}\b", 0.99),
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
    patterns=dob_patterns,
    name="DOB_Recognizer"
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
    global_regex_flags=re.IGNORECASE | re.MULTILINE,
    name="Street_Recognizer"
)

# ZIP Code
zip_patterns = [
    Pattern("ZIP Code", r"\b\d{5}(?:-\d{4})?\b", 0.99)
]

ZipRecognizer = PatternRecognizer(
    supported_entity="ZIP_CODE",
    patterns=zip_patterns,
    context=["Zip", "Postal", "IL", "AZ", "NY", "CA", "TX"],
    global_regex_flags=re.IGNORECASE | re.MULTILINE,
    name="Zip_Recognizer"
)

# Age Recognizer (Force match for redact check)
age_patterns = [
    Pattern("Age pattern", r"\b\d{1,3}\s*(?:year|yr)s?\s*old\b", 0.95),
    Pattern("Age value", r"\bAge:\s*\d{1,3}\b", 0.95),
]
AgeRecognizer = PatternRecognizer(
    supported_entity="AGE",
    patterns=age_patterns,
    context=["Age", "years", "old"],
    name="Age_Recognizer"
)

# National Provider Identifier
npi_patterns = [
    Pattern("NPI Digits", r"\b\d{10}\b", 0.85)
]

NPIRecognizer = PatternRecognizer(
    supported_entity="NPI",
    patterns=npi_patterns,
    context=["Provider", "NPI"],
    global_regex_flags=re.IGNORECASE | re.MULTILINE,
    name="NPI_Recognizer"
)

# Insurance Policy
insurance_patterns = [
    Pattern("Insurance Policy", r"\b[A-Z]{2,6}-[A-Z]{2,6}-\d{5,12}\b", 0.99)
]

InsuranceRecognizer = PatternRecognizer(
    supported_entity="INSURANCE_ID", 
    patterns=insurance_patterns,
    context=["Policy", "Group", "Insurance", "BCBS", "Aetna", "Cigna", "United"],
    global_regex_flags=re.IGNORECASE | re.MULTILINE,
    name="Insurance_Recognizer"
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
    context=["Emergency", "Spouse", "Contact", "Relationship"],
    name="EmergencyContact_Recognizer"
)

# Device ID / Account Number / Auth Tokens
account_patterns = [
    Pattern("ID Pattern", r"\b[A-Z]{2,4}-\d{4,15}\b", 0.95),
    Pattern("Dev ID Pattern", r"\bDEV-\d{4,10}\b", 0.95),
    Pattern("BF Pattern", r"\bBF-\d{4,15}\b", 0.95),
    Pattern("FaceScan Pattern", r"\b(?:FACESCAN|FACE)-\d{4,8}\b", 0.95),
    Pattern("BioToken Pattern", r"\b(?:BIO|RET|FP)-\d{4,12}\b", 0.95),
]
AccountRecognizer = PatternRecognizer(
    supported_entity="ID",
    patterns=account_patterns,
    context=["ID", "Account", "Device", "Passport", "License", "Fingerprint", "Scan", "Authentication", "Token", "Biometric"],
    name="Account_Recognizer"
)

# Vehicle Plate (HIPAA Category #15) / VIN / Parking
vehicle_patterns = [
    Pattern("Vehicle Plate", r"\b[A-Z]{2}-[A-Z]{2,4}-\d{4}\b", 0.95),
    Pattern("State Plate", r"\b[A-Z]{2}-\d{4}-[A-Z]{2}\b", 0.95),
    Pattern("VIN", r"\b[A-HJ-NPR-Z0-9]{17}\b", 0.95),
    Pattern("Parking Permit", r"\bPP-\d{4,8}\b", 0.95),
]
VehiclePlateRecognizer = PatternRecognizer(
    supported_entity="VEHICLE_PLATE",
    patterns=vehicle_patterns,
    context=["Plate", "Vehicle", "VIN", "License Plate", "Parking", "Permit"],
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

# Coordinates (Latitude / Longitude)
coordinate_patterns = [
    # Decimal Degrees with Optional Direction: 40.7128 N, 74.0060 W
    Pattern("Decimal Coordinates", r"\b-?\d{1,3}\.\d{3,10}[°\s]*[NSEW]?\s*,?\s*-?\d{1,3}\.\d{3,10}[°\s]*[NSEW]?\b", 0.95),
    # Labeled Decimal: Lat: 40.7128, Long: -74.0060
    Pattern("Labeled Latitude", r"\bLat(?:itude)?[:\s]*-?\d{1,3}\.\d{3,10}[°\s]*[NS]?\b", 0.95),
    Pattern("Labeled Longitude", r"\bLong?(?:itude)?[:\s]*-?\d{1,3}\.\d{3,10}[°\s]*[EW]?\b", 0.95),
    # Degrees Minutes Seconds: 40° 42' 46" N
    Pattern("DMS Coordinates", r"\b\d{1,3}°\s*\d{1,2}'\s*\d{1,2}(?:\.\d+)?\"\s*[NSEW]\b", 0.95),
]

CoordinateRecognizer = PatternRecognizer(
    supported_entity="COORDINATE",
    patterns=coordinate_patterns,
    context=["coordinate", "location", "lat", "long", "gps"],
    global_regex_flags=re.IGNORECASE | re.MULTILINE,
    name="Coordinate_Recognizer"
)

# Credit Cards & Payments
credit_card_patterns = [
    Pattern("Credit Card", r"\b(?:\d{4}[-\s]?){3}\d{4}\b", 0.95),
]
CreditCardRecognizer = PatternRecognizer(
    supported_entity="CREDIT_CARD",
    patterns=credit_card_patterns,
    context=["Credit", "Card", "Visa", "Mastercard", "Amex"],
    name="CreditCard_Recognizer"
)
cvv_patterns = [
    Pattern("CVV", r"\bCVV[:\s]*\d{3,4}\b", 0.99)
]
CVVRecognizer = PatternRecognizer(
    supported_entity="ID", 
    patterns=cvv_patterns,
    name="CVV_Recognizer"
)
# Usernames
username_patterns = [
    Pattern("Labeled Username", r"\b(?:Username|User\s*ID|Login|Portal\s*Username)[:\s]+([a-zA-Z0-9._-]+)\b", 0.99),
    Pattern("Username", r"\b[a-z][a-z0-9._-]*[0-9._-]+[a-z0-9._-]*\b", 0.80)
]
UsernameRecognizer = PatternRecognizer(
    supported_entity="USERNAME",
    patterns=username_patterns,
    context=["user", "username", "login", "portal"],
    global_regex_flags=re.IGNORECASE,
    name="Username_Recognizer"
)

# Patient Filenames
filename_patterns = [
    Pattern("Generic Filename", r"\b[a-zA-Z0-9._-]+\.(?:jpg|jpeg|png|gif|pdf|doc|docx|txt|dcm|tif|tiff|csv|xls|xlsx|ppt|pptx|mp4|avi|mov|zip|rtf)\b", 0.90)
]
FilenameRecognizer = PatternRecognizer(
    supported_entity="FILENAME",
    patterns=filename_patterns,
    context=["file", "photo", "image", "upload", "attachment", "scan", "mri", "xray", "ct", "dicom"],
    global_regex_flags=re.IGNORECASE,
    name="Filename_Recognizer"
)

# Alias / AKA detection (explicitly labeled alternative names)
alias_patterns = [
    Pattern("Alias Label", r"\b(?:Alias|AKA|Also known as|Goes by)[:\s]+([A-Z][a-z]+(?:\s[A-Z][a-z]+){0,3})\b", 0.99),
]
AliasRecognizer = PatternRecognizer(
    supported_entity="PERSON",
    patterns=alias_patterns,
    context=["alias", "aka", "known", "name"],
    name="Alias_Recognizer"
)

# Claims and Policy Numbers
claim_patterns = [
    Pattern("Policy", r"\bPOL-\d{6,10}\b", 0.95),
    Pattern("Claim", r"\bCLM-\d{5,10}\b", 0.95),
    Pattern("Group", r"\bGRP-\d{4,10}\b", 0.95),
]
ClaimRecognizer = PatternRecognizer(
    supported_entity="ID",
    patterns=claim_patterns,
    context=["Claim", "Policy", "Group"],
    name="Claim_Recognizer"
)

# Lab Orders and Sample IDs
lab_patterns = [
    Pattern("Lab Order", r"\bLAB-\d{4,10}\b", 0.95),
    Pattern("Sample ID", r"\bSMP-\d{4,10}\b", 0.95),
]
LabRecognizer = PatternRecognizer(
    supported_entity="ID",
    patterns=lab_patterns,
    context=["Lab", "Order", "Sample", "Test"],
    name="Lab_Recognizer"
)

# Medicare / Prescription / Internal Case IDs
medical_id_patterns = [
    Pattern("Medicare MBI", r"\b[1-9][A-Z][0-9A-Z][0-9]-[A-Z][0-9A-Z][0-9]-[A-Z]{2}[0-9]{2}\b", 0.99),
    Pattern("Prescription RX", r"\bRX-\d{4,10}\b", 0.95),
    Pattern("Internal Case ID", r"\bCASE-\d{4}-\d{5,10}\b", 0.95),
]
MedicalIDRecognizer = PatternRecognizer(
    supported_entity="ID",
    patterns=medical_id_patterns,
    context=["Medicare", "MBI", "Prescription", "RX", "Case", "ID"],
    name="Medical_ID_Recognizer"
)

# ── Aggregated list of all custom recognizer instances ────────────────────────
ALL_RECOGNIZERS = [
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
    CreditCardRecognizer,
    CVVRecognizer,
    UsernameRecognizer,
    FilenameRecognizer,
    AliasRecognizer,
    ClaimRecognizer,
    LabRecognizer,
    MedicalIDRecognizer,
    CountyRecognizer,
    UrlRecognizer,
]
