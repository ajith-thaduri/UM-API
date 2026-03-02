import sys
sys.path.append("/Users/ajiththaduri/Desktop/V2/UM-API")
from scripts.test_deid_rich_text import TEST_TEXT
from app.services.date_shift_service import shift_dates_in_text

shift_days = 28 # Use a large shift to be sure
shifted = shift_dates_in_text(TEST_TEXT, shift_days, 1)

print(f"Shift days: {shift_days}")
if "03/20/2025" in shifted:
    print("❌ FAILED: 03/20/2025 still present in shifted text.")
    # Find context
    idx = shifted.find("03/20/2025")
    print(f"Context: ...{shifted[idx-20:idx+30]}...")
else:
    print("✅ SUCCESS: 03/20/2025 was shifted.")
    # Look for the shifted version (03/20 + 28 days = 04/17)
    if "04/17/2025" in shifted:
        print("✅ SUCCESS: Found shifted date 04/17/2025.")
    else:
        print("❓ WARNING: 03/20/2025 is gone but 04/17/2025 not found. Checking if it's there at all...")
        # Maybe it shifted to something else or I miscalculated
        import re
        dates = re.findall(r"\d{1,2}/\d{1,2}/\d{4}", shifted)
        print(f"Dates found in shifted text: {dates}")

# Check 03/02/2025 as well
if "03/02/2025" in shifted:
     print("❌ FAILED: 03/02/2025 still present.")
else:
     print("✅ SUCCESS: 03/02/2025 was shifted.")
