import pytest
from fastapi import status
from app.models.user import User
from app.models.prompt import Prompt
from app.services.auth_service import create_access_token

def get_auth_headers(client, email="test@example.com", password="password123"):
    """Helper to register and get auth token."""
    reg_data = {"email": email, "password": password, "name": "Test User"}
    response = client.post("/api/v1/auth/register", json=reg_data)
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}

def test_list_prompts(client, db):
    """Test listing prompts."""
    headers = get_auth_headers(client, "prompts@example.com")
    
    # Create a test prompt
    prompt = Prompt(
        id="test-prompt-1",
        category="test",
        name="Test Prompt",
        template="Test template {variable}",
        variables=["variable"],
        is_active=True
    )
    db.add(prompt)
    db.commit()
    
    response = client.get("/api/v1/prompts", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    assert isinstance(response.json(), list)

def test_get_prompt(client, db):
    """Test getting a specific prompt."""
    headers = get_auth_headers(client, "getprompt@example.com")
    
    # Create a test prompt
    prompt = Prompt(
        id="test-prompt-2",
        category="test",
        name="Test Prompt 2",
        template="Template {var}",
        variables=["var"],
        is_active=True
    )
    db.add(prompt)
    db.commit()
    
    response = client.get("/api/v1/prompts/test-prompt-2", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["id"] == "test-prompt-2"

def test_get_prompt_not_found(client, db):
    """Test getting non-existent prompt."""
    headers = get_auth_headers(client, "notfound@example.com")
    response = client.get("/api/v1/prompts/non-existent", headers=headers)
    assert response.status_code == status.HTTP_404_NOT_FOUND

def test_update_prompt(client, db):
    """Test updating a prompt."""
    headers = get_auth_headers(client, "update@example.com")
    
    # Create a test prompt
    prompt = Prompt(
        id="test-prompt-3",
        category="test",
        name="Test Prompt 3",
        template="Old template",
        variables=[],
        is_active=True
    )
    db.add(prompt)
    db.commit()
    
    # Update prompt
    update_data = {
        "template": "New template",
        "system_message": "System message",
        "change_notes": "Updated for testing"
    }
    response = client.put(
        "/api/v1/prompts/test-prompt-3",
        json=update_data,
        headers=headers
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["success"] is True

def test_get_prompt_versions(client, db):
    """Test getting prompt version history."""
    headers = get_auth_headers(client, "versions@example.com")
    
    # Create and update a prompt to generate history
    prompt = Prompt(
        id="test-prompt-4",
        category="test",
        name="Test Prompt 4",
        template="Original",
        variables=[],
        is_active=True
    )
    db.add(prompt)
    db.commit()
    
    # Update to create history
    client.put(
        "/api/v1/prompts/test-prompt-4",
        json={"template": "Updated"},
        headers=headers
    )
    
    # Get versions
    response = client.get("/api/v1/prompts/test-prompt-4/versions", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    assert isinstance(response.json(), list)

def test_list_prompts_by_category(client, db):
    """Test listing prompts filtered by category."""
    headers = get_auth_headers(client, "category@example.com")
    
    # Create prompts in different categories
    prompt1 = Prompt(
        id="cat1-prompt",
        category="category1",
        name="Cat1 Prompt",
        template="Template",
        variables=[],
        is_active=True
    )
    prompt2 = Prompt(
        id="cat2-prompt",
        category="category2",
        name="Cat2 Prompt",
        template="Template",
        variables=[],
        is_active=True
    )
    db.add(prompt1)
    db.add(prompt2)
    db.commit()
    
    response = client.get("/api/v1/prompts?category=category1", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    prompts = response.json()
    assert all(p["category"] == "category1" for p in prompts)
