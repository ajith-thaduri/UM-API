import sys
import os
import re
sys.path.insert(0, r"c:\Users\DELL\Desktop\UM\UM_backend")

# Mock the logger
from unittest.mock import MagicMock
sys.modules['app.utils.safe_logger'] = MagicMock()

from app.api.endpoints.presidio_tools import analyze_text_advanced, AdvancedAnalyzeRequest

# The exact text from the user's scenario
text = """Danny Anderson, born on 29/02/1944.
Past Hospital Visits
15/08/2024
22/05/2024
18/08/2023
25/05/2023
03/11/2024
10/02/2024
05/11/2023
01/11/2024
"""

request = AdvancedAnalyzeRequest(
    text=text,
    score_threshold=0.35,
    de_id_approach="replace",
    date_shift_days=5
)

response = analyze_text_advanced(request)

print("Entities (Findings Table in UI):")
for e in response.entities:
    # Only show dates to declutter
    if e.entity_type == "DATE_TIME":
        print(f"[{e.entity_type}] {e.text} (Score: {e.score}) -> {e.explanation}")

print("\nDate Shifts (Date Shifts Table in UI):")
for s in response.date_shifts:
    print(f"Original: {s.original} -> Shifted: {s.shifted}")
