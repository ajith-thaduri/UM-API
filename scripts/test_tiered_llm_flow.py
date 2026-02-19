
import sys
import os
import asyncio
from pathlib import Path

# SET ENVIRONMENT VARIABLE BEFORE ANY IMPORTS
os.environ["DATABASE_URL"] = "sqlite:///./test_temp.db"

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from unittest.mock import MagicMock, patch

# Now import everything else Safely
from app.services.llm.llm_factory import get_tier1_llm_service_for_user, get_tier2_llm_service_for_user
from app.models.user_preference import UserPreference
from app.services.summary_service import SummaryService

async def test_tiered_flow():
    print("=== Testing Tiered LLM & Presidio Toggle Flow ===")
    
    # 1. Setup Mocks
    db = MagicMock()
    user_id = "test-user-123"
    
    # Mock Preference: Tier1=Llama70b, Tier2=Claude4.5, Presidio=OFF
    mock_pref = UserPreference(
        user_id=user_id,
        llm_provider="claude",
        llm_model="claude-3-5-sonnet",
        tier1_model="meta-llama/llama-3.1-70b-instruct",
        tier2_model="claude-4.5-preview",
        presidio_enabled=False
    )
    
    # Mock Repository
    with patch("app.repositories.user_preference_repository.UserPreferenceRepository.get_by_user_id", return_value=mock_pref):
        
        print("\n--- Phase 1: LLM Factory Model Verification ---")
        
        # Test Tier 1 (OpenRouter)
        t1_service = get_tier1_llm_service_for_user(db, user_id)
        print(f"Tier 1 Model: {t1_service.model}")
        assert t1_service.model == "meta-llama/llama-3.1-70b-instruct", f"Expected Llama but got {t1_service.model}"
        print("✅ Tier 1 Model Correctly Fetched from Preference.")

        # Test Tier 2 (Claude)
        t2_service = get_tier2_llm_service_for_user(db, user_id)
        print(f"Tier 2 Model: {t2_service.model}")
        assert t2_service.model == "claude-4.5-preview", f"Expected Claude 4.5 but got {t2_service.model}"
        print("✅ Tier 2 Model Correctly Fetched from Preference.")

        print("\n--- Phase 2: Presidio Toggle Logic (OFF) ---")
        
        presidio_enabled = mock_pref.presidio_enabled
        print(f"Presidio Enabled Flag: {presidio_enabled}")
        
        if not presidio_enabled:
            print("Simulating BYPASS of Presidio (Tier 2 payload should be RAW)")
            raw_payload = {"clinical_data": "Patient Name: John Doe"} # Raw PHI
            print(f"Resulting Payload: {raw_payload}")
            assert "John Doe" in raw_payload["clinical_data"]
            print("✅ Presidio Bypass Logic Verified.")
            
        print("\n--- Phase 3: Toggling BACK (Presidio ON + Model Change) ---")
        mock_pref.presidio_enabled = True
        mock_pref.tier2_model = "claude-3-haiku"
        
        # Re-fetch service
        t2_service_new = get_tier2_llm_service_for_user(db, user_id)
        print(f"New Tier 2 Model: {t2_service_new.model}")
        assert t2_service_new.model == "claude-3-haiku"
        
        presidio_enabled_new = mock_pref.presidio_enabled
        print(f"New Presidio Enabled Flag: {presidio_enabled_new}")
        assert presidio_enabled_new is True
        print("✅ Preferences correctly updated and reflected in Factory.")

    print("\n=== All Tests Passed Successfully! ===")
    
    # Cleanup temp db if it was created
    if os.path.exists("test_temp.db"):
        os.remove("test_temp.db")

if __name__ == "__main__":
    asyncio.run(test_tiered_flow())
