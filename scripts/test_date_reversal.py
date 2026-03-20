
import sys
import os
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from app.services.date_shift_service import date_shift_service

def test_date_reversal():
    print("=== Testing Date Reversal Logic ===\n")
    
    # Positive shift (sent to Claude)
    shift_days = 10
    
    from app.services.date_shift_service import shift_dates_in_text
    
    # Original clinical text
    original_text = "Patient admitted on 05/12/2024 and discharged on 2024-05-20. Follow up on Jan 15, 2025."
    
    # Shift forward (direction=1)
    shifted_text = shift_dates_in_text(original_text, shift_days, direction=1)
    print(f"Original: {original_text}")
    print(f"Shifted:  {shifted_text}")
    
    # Reverse shift (direction=-1)
    reversed_text = date_shift_service.reidentify_summary_text(shifted_text, shift_days)
    print(f"Reversed: {reversed_text}")
    
    # Verification
    # Note: Jan 15, 2025 becomes 01/25/2025 then 01/15/2025.
    # Note: %m/%d/%Y is the target format for shifted dates
    
    expected_admit = "05/12/2024"
    expected_discharge = "05/20/2024" # Note: ISO usually converted to MM/DD/YYYY by service
    expected_followup = "01/15/2025"
    
    for date in [expected_admit, expected_discharge, expected_followup]:
        if date in reversed_text:
            print(f"✅ Found {date} in reversed text")
        else:
            print(f"❌ Missing {date} in reversed text")

if __name__ == "__main__":
    test_date_reversal()
