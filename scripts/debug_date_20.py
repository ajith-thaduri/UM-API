import sys
sys.path.append("/Users/ajiththaduri/Desktop/V2/UM-API")
from app.services.date_shift_service import shift_dates_in_text

text = "Date: 03/20/2025"
shifted = shift_dates_in_text(text, 10, 1)
print(f"Original: {text}")
print(f"Shifted (10 days): {shifted}")

if shifted == "Date: 03/30/2025":
    print("SUCCESS")
else:
    print("FAILED")
