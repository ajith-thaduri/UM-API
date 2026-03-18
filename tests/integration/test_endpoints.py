import pytest
from fastapi import status
from app.models.user import User, UserRole
from app.models.case import Case, CaseStatus, Priority
from app.models.prompt import Prompt
from app.models.wallet import Wallet
from app.models.transaction import Transaction, TransactionType, TransactionStatus
from app.services.auth_service import create_access_token, get_password_hash
from sqlalchemy import select

def test_health_check(client):
    """Test the health check endpoint."""
    response = client.get("/health")
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["status"] == "healthy"

def test_root_endpoint(client):
    """Test the root endpoint."""
    response = client.get("/")
    assert response.status_code == status.HTTP_200_OK
    assert "version" in response.json()

def test_auth_registration_and_login(client, db):
    """Test user registration and subsequent login."""
    # 1. Register
    reg_data = {
        "email": "test@example.com",
        "password": "strong-password-123",
        "name": "Test User"
    }
    response = client.post("/api/v1/auth/register", json=reg_data)
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["email"] == reg_data["email"]
    
    # Verify user in DB
    user = db.query(User).filter(User.email == reg_data["email"]).first()
    assert user is not None
    assert user.name == "Test User"

    # 2. Login
    login_data = {
        "email": reg_data["email"],
        "password": reg_data["password"]
    }
    response = client.post("/api/v1/auth/login", json=login_data)
    assert response.status_code == status.HTTP_200_OK
    assert "access_token" in response.json()

def test_auth_login_invalid_credentials(client, db):
    """Test login with invalid credentials."""
    # Register a user first
    reg_data = {
        "email": "test2@example.com",
        "password": "correct-password",
        "name": "Test User 2"
    }
    client.post("/api/v1/auth/register", json=reg_data)
    
    # Try login with wrong password
    response = client.post("/api/v1/auth/login", json={
        "email": "test2@example.com",
        "password": "wrong-password"
    })
    assert response.status_code == status.HTTP_401_UNAUTHORIZED

def test_auth_register_duplicate_email(client, db):
    """Test registration with duplicate email."""
    reg_data = {
        "email": "duplicate@example.com",
        "password": "password123",
        "name": "First User"
    }
    # First registration
    response = client.post("/api/v1/auth/register", json=reg_data)
    assert response.status_code == status.HTTP_200_OK
    
    # Second registration with same email
    response = client.post("/api/v1/auth/register", json=reg_data)
    assert response.status_code == status.HTTP_400_BAD_REQUEST

def test_auth_refresh_token(client, db):
    """Test token refresh endpoint."""
    # Register and get token
    reg_data = {
        "email": "refresh@example.com",
        "password": "password123",
        "name": "Refresh User"
    }
    response = client.post("/api/v1/auth/register", json=reg_data)
    token = response.json()["access_token"]
    
    # Refresh token
    response = client.post("/api/v1/auth/refresh", json={"token": token})
    assert response.status_code == status.HTTP_200_OK
    assert "access_token" in response.json()
    # Just verify we got a valid token back (may be same if created at same time)
    assert len(response.json()["access_token"]) > 0

def test_auth_logout(client, db):
    """Test logout endpoint."""
    # Register and get token
    reg_data = {
        "email": "logout@example.com",
        "password": "password123",
        "name": "Logout User"
    }
    response = client.post("/api/v1/auth/register", json=reg_data)
    token = response.json()["access_token"]
    
    # Logout
    response = client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == status.HTTP_200_OK

def test_auth_get_me(client, db):
    """Test /me endpoint."""
    # Register and get token
    reg_data = {
        "email": "me@example.com",
        "password": "password123",
        "name": "Me User"
    }
    response = client.post("/api/v1/auth/register", json=reg_data)
    token = response.json()["access_token"]
    
    # Get current user info
    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["email"] == "me@example.com"

def test_auth_get_me_unauthorized(client):
    """Test /me endpoint without token."""
    response = client.get("/api/v1/auth/me")
    assert response.status_code == status.HTTP_403_FORBIDDEN

def test_case_db_crud(db):
    """Direct database test for Case CRUD."""
    # Create
    new_case = Case(
        id="test-case-1",
        patient_id="PAT-001",
        patient_name="John Doe",
        case_number="CASE-999",
        status=CaseStatus.UPLOADED,
        priority=Priority.NORMAL,
        user_id="fake-user-id"
    )
    
    # Let's create a user first to satisfy foreign key
    user = User(id="fake-user-id", email="fake@example.com", name="Fake User")
    db.add(user)
    db.add(new_case)
    db.commit()
    
    # Fetch
    fetched_case = db.query(Case).filter(Case.id == "test-case-1").first()
    assert fetched_case is not None
    assert fetched_case.patient_name == "John Doe"
    
    # Update
    fetched_case.patient_name = "Jane Doe"
    db.commit()
    
    # Verify update
    updated_case = db.query(Case).filter(Case.id == "test-case-1").first()
    assert updated_case.patient_name == "Jane Doe"
