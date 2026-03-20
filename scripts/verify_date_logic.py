import sys
from unittest.mock import MagicMock

# 1. Proactively mock heavy dependencies BEFORE they are imported
sys.modules['app.db'] = MagicMock()
sys.modules['app.db.session'] = MagicMock()
sys.modules['app.core.config'] = MagicMock()
sys.modules['app.utils.safe_logger'] = MagicMock()

# Setup path
import os
sys.path.insert(0, r"c:\Users\DELL\Desktop\UM\UM_backend")

# 2. Imports
from app.utils.date_utils import is_strict_dd_mm_yyyy
from app.services.date_shift_service import shift_dates_in_text
from app.services.presidio.date_handler import shift_single_date

# 3. Test Cases
print("--- TEST CASE: Narrative Text ---")
text = "Born: 29/02/1944. Shiftable: 03/11/2024. Leaking: 15/08/2024."
shifted = shift_dates_in_text(text, shift_days=5, direction=1)
print(f"Original: {text}")
print(f"Result  : {shifted}")

print("\n--- TEST CASE: Structured Data ---")
for d in ["29/02/1944", "03/11/2024", "15/08/2024"]:
    res = shift_single_date(d, shift_days=5)
    print(f"{d} -> {res}")

# 4. Assertions
assert "[[REDACTED]]" in shifted, "29/02/1944 should be redacted"
assert "03/16/2024" in shifted, "03/11/2024 should be shifted"
assert shifted.count("[[REDACTED]]") >= 2, "Both 29/02 and 15/08 should be redacted"

print("\nLogic Verification PASSED!")
