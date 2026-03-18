import pytest
from fastapi import status
from app.models.user import User
from app.models.user_preference import UserPreference

def get_auth_headers(client, email="prefs@example.com", password="password123"):
    """Helper to register and get auth token."""
    reg_data = {"email": email, "password": password, "name": "Test User"}
    response = client.post("/api/v1/auth/register", json=reg_data)
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}

def test_get_user_preferences(client, db):
    """Test getting user preferences."""
    headers = get_auth_headers(client, "getprefs@example.com")
    
    response = client.get("/api/v1/user/preferences", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    assert "llm_provider" in response.json()
    assert "llm_model" in response.json()

def test_update_user_preferences(client, db):
    """Test updating user preferences."""
    headers = get_auth_headers(client, "updateprefs@example.com")
    
    pref_data = {
        "llm_provider": "openai",
        "llm_model": "gpt-4o"
    }
    response = client.put("/api/v1/user/preferences", json=pref_data, headers=headers)
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["llm_provider"] == "openai"

def test_update_user_preferences_invalid_provider(client, db):
    """Test updating preferences with invalid provider."""
    headers = get_auth_headers(client, "invalidprovider@example.com")
    
    pref_data = {
        "llm_provider": "invalid-provider",
        "llm_model": "gpt-4o"
    }
    response = client.put("/api/v1/user/preferences", json=pref_data, headers=headers)
    assert response.status_code == status.HTTP_400_BAD_REQUEST

def test_update_user_preferences_empty_model(client, db):
    """Test updating preferences with empty model."""
    headers = get_auth_headers(client, "emptymodel@example.com")
    
    pref_data = {
        "llm_provider": "openai",
        "llm_model": ""
    }
    response = client.put("/api/v1/user/preferences", json=pref_data, headers=headers)
    assert response.status_code == status.HTTP_400_BAD_REQUEST

def test_get_available_models_openai(client, db):
    """Test getting available OpenAI models."""
    headers = get_auth_headers(client, "modelsopenai@example.com")
    
    response = client.get("/api/v1/user/preferences/models?provider=openai", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["provider"] == "openai"
    assert len(response.json()["models"]) > 0

def test_get_available_models_claude(client, db):
    """Test getting available Claude models."""
    headers = get_auth_headers(client, "modelsclaude@example.com")
    
    response = client.get("/api/v1/user/preferences/models?provider=claude", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["provider"] == "claude"
    assert len(response.json()["models"]) > 0

def test_get_available_models_invalid_provider(client, db):
    """Test getting models for invalid provider."""
    headers = get_auth_headers(client, "invalidmodels@example.com")
    
    response = client.get("/api/v1/user/preferences/models?provider=invalid", headers=headers)
    assert response.status_code == status.HTTP_400_BAD_REQUEST
