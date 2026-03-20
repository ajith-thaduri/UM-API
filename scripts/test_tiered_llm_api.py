
import sys
import os
import requests
import json
from pathlib import Path

# SET ENVIRONMENT VARIABLE BEFORE ANY IMPORTS
os.environ["DATABASE_URL"] = "sqlite:///./test_api_temp.db"

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

def test_api_sync():
    """
    Simulates the API calls that the frontend makes.
    Note: This assumes the backend is running. 
    If not, we can test the Pydantic schemas and transformation logic.
    """
    print("=== Testing Tiered LLM API Integration (Schemas) ===")
    
    # Import schemas
    from app.api.endpoints.user_preferences import UserPreferenceRequest, UserPreferenceResponse
    from datetime import datetime
    
    # 1. Test Request Schema
    req_data = {
        "llm_provider": "openai",
        "llm_model": "gpt-4o",
        "presidio_enabled": False,
        "tier1_model": "meta-llama/llama-3.1-405b",
        "tier2_model": "claude-3-opus"
    }
    
    req = UserPreferenceRequest(**req_data)
    print(f"✅ Request Object Created: {req.dict()}")
    assert req.tier1_model == "meta-llama/llama-3.1-405b"
    assert req.presidio_enabled is False
    
    # 2. Test Response Schema
    res_data = {
        "llm_provider": "openai",
        "llm_model": "gpt-4o",
        "tier1_model": "meta-llama/llama-3.1-405b",
        "tier2_model": "claude-3-opus",
        "presidio_enabled": False,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat()
    }
    
    res = UserPreferenceResponse(**res_data)
    print(f"✅ Response Object Created: {res.dict()}")
    assert res.tier2_model == "claude-3-opus"
    
    # 3. Test Partial Fields
    partial_req = UserPreferenceRequest(
        llm_provider="claude",
        llm_model="claude-3-5-sonnet",
        tier1_model="meta-llama/llama-3.1-70b-instruct"
    )
    print(f"✅ Partial Request (Enforced): {partial_req.dict()}")
    assert partial_req.tier1_model == "meta-llama/llama-3.1-70b-instruct"
    
    print("\n=== API Schema Tests Passed! ===")

if __name__ == "__main__":
    test_api_sync()
