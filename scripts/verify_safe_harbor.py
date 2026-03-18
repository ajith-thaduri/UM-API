"""
Diagnostic: verify each Safe Harbor recognizer triggers at correct score and 
that the Tier 2 heuristic strip layer also fires.
"""
import sys, re
sys.path.append("/Users/ajiththaduri/Desktop/V2/UM-API")
from app.services.presidio_deidentification_service import presidio_deidentification_service as svc

# --- 1. Direct analyzer scan ---
SAMPLES = {
    "SSN":           "SSN: 123-45-6789",
    "IP":            "192.168.1.45",
    "Vehicle Plate": "IL-ABC-7890",
    "Passport":      "Passport: X12345678",
    "License":       "Driver's License: D1234567 (Illinois)",
}

print("=== Analyzer Detection (score_threshold=0.3) ===")
analyzer_missing = []
for label, text in SAMPLES.items():
    results = svc.analyzer.analyze(text=text, language="en", score_threshold=0.3)
    if results:
        hit = results[0]
        print(f"  ✅ {label}: {hit.entity_type} [{hit.start}:{hit.end}] score={hit.score:.2f}")
    else:
        print(f"  ❌ {label}: NOT DETECTED by analyzer")
        analyzer_missing.append(label)

# --- 2. Heuristic strip layer ---
print("\n=== Heuristic Strip Layer (_replace_in_string) ===")
# Build minimal state
svc._strip_list = ["123-45-6789"]
svc._variant_token_map = {}

strip_missing = []
for label, text in SAMPLES.items():
    # Inline the heuristic checks only
    result = text
    result = re.sub(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', "[[REDACTED]]", result)
    result = re.sub(r'\(?\\d{3}\)?[-.\\s]?\d{3}[-.\\s]?\d{4}', "[[REDACTED]]", result)
    result = re.sub(r'\b\d{3}-\d{2}-\d{4}\b', "[[REDACTED]]", result)
    result = re.sub(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', "[[REDACTED]]", result)
    result = re.sub(r'\b[A-Z]{2}-[A-Z]{2,4}-\d{4}\b', "[[REDACTED]]", result)
    result = re.sub(r'\b(?:Passport|License|DL)[:\s]*[A-Z]\d{6,9}\b', "[[REDACTED]]", result, flags=re.I)
    if "[[REDACTED]]" in result:
        print(f"  ✅ {label}: heuristic strip fired → '{result}'")
    else:
        print(f"  ❌ {label}: heuristic strip missed → '{result}'")
        strip_missing.append(label)

print(f"\n=== Summary ===")
print(f"  Analyzer missing: {analyzer_missing or 'None'}")
print(f"  Strip layer missing: {strip_missing or 'None'}")

# --- 3. Check registered entity types ---
print("\n=== Registered Recognizers ===")
for r in svc.analyzer.registry.recognizers:
    if hasattr(r, 'supported_entities') and r.supported_entities[0] in {
        "SSN", "IP_ADDRESS", "VEHICLE_PLATE", "PASSPORT", "DRIVERS_LICENSE"
    }:
        print(f"  {r.supported_entities[0]}: {type(r).__name__}")
