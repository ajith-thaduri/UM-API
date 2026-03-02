import sys
sys.path.append("/Users/ajiththaduri/Desktop/V2/UM-API")
from app.services.presidio_deidentification_service import presidio_deidentification_service

text = "Admission Date: 03/02/2025"
shifted = presidio_deidentification_service._shift_dates_in_text(text, 10)
print(f"Original: {text}")
print(f"Shifted (10 days): {shifted}")

if shifted == "Admission Date: 03/12/2025":
    print("SUCCESS: Regex shifter works.")
else:
    print("FAILED: Regex shifter failed.")
