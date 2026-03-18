import asyncio
import sys
from copy import deepcopy
sys.path.append("/Users/ajiththaduri/Desktop/V2/UM-API")
from app.services.presidio_deidentification_service import presidio_deidentification_service
from scripts.test_deid_rich_text import TEST_TEXT

async def debug_pipeline_shifts():
    clinical_data = {"summary": TEST_TEXT}
    shift_days = 20
    
    # Step 5 style call
    shifted_data, shifted_fields = presidio_deidentification_service._shift_dates_structured(
        clinical_data, shift_days, path="clinical_data"
    )
    
    print(f"Total shifts found: {len(shifted_fields)}")
    found_20 = False
    for s in shifted_fields:
        if "03/20/2025" in s["original"]:
            print(f"✅ FOUND 03/20/2025 shift: {s}")
            found_20 = True
            
    if not found_20:
        print("❌ FAILED: 03/20/2025 not found in shifted_fields.")
        # Check summary text directly
        if "03/20/2025" in shifted_data["summary"]:
            print("❌ CONFIRMED: 03/20/2025 is still in shifted_data['summary'].")
        else:
            print("✅ OK: 03/20/2025 is NOT in shifted_data['summary']. (So it shifted!)")

if __name__ == "__main__":
    asyncio.run(debug_pipeline_shifts())
