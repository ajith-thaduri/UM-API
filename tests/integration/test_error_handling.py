import pytest
from fastapi import status
from app.models.user import User

def get_auth_headers(client, email="error@example.com", password="password123"):
    """Helper to register and get auth token."""
    reg_data = {"email": email, "password": password, "name": "Test User"}
    response = client.post("/api/v1/auth/register", json=reg_data)
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}

def test_404_not_found(client):
    """Test 404 error handling."""
    response = client.get("/api/v1/non-existent-endpoint")
    assert response.status_code == status.HTTP_404_NOT_FOUND

def test_401_unauthorized(client):
    """Test 401 unauthorized error."""
    # Try to access protected endpoint without token
    response = client.get("/api/v1/auth/me")
    assert response.status_code == status.HTTP_403_FORBIDDEN  # FastAPI returns 403 for missing auth

def test_400_bad_request(client, db):
    """Test 400 bad request error."""
    headers = get_auth_headers(client, "badrequest@example.com")
    
    # Try to register with invalid email
    response = client.post("/api/v1/auth/register", json={
        "email": "invalid-email",
        "password": "password123",
        "name": "Test"
    })
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY  # Pydantic validation

def test_400_duplicate_email(client, db):
    """Test 400 error for duplicate email."""
    reg_data = {
        "email": "duplicate400@example.com",
        "password": "password123",
        "name": "First User"
    }
    client.post("/api/v1/auth/register", json=reg_data)
    
    # Try to register again
    response = client.post("/api/v1/auth/register", json=reg_data)
    assert response.status_code == status.HTTP_400_BAD_REQUEST

def test_invalid_token_format(client):
    """Test invalid token format."""
    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer invalid-token-format"}
    )
    assert response.status_code in [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN]

def test_prompt_not_found_error(client, db):
    """Test 404 error for non-existent prompt."""
    headers = get_auth_headers(client, "prompterror@example.com")
    response = client.get("/api/v1/prompts/non-existent-prompt-id", headers=headers)
    assert response.status_code == status.HTTP_404_NOT_FOUND

def test_wallet_endpoint_requires_auth(client):
    """Test that wallet endpoints require authentication."""
    response = client.get("/api/v1/wallet/balance")
    assert response.status_code == status.HTTP_403_FORBIDDEN

def test_invalid_json_payload(client):
    """Test handling of invalid JSON."""
    headers = get_auth_headers(client, "jsonerror@example.com")
    response = client.post(
        "/api/v1/wallet/add-funds",
        data="invalid json",
        headers={**headers, "Content-Type": "application/json"}
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
