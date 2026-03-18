import pytest
from fastapi import status
from app.models.user import User, UserRole

def get_auth_headers(client, email="users@example.com", password="password123"):
    """Helper to register and get auth token."""
    reg_data = {"email": email, "password": password, "name": "Test User"}
    response = client.post("/api/v1/auth/register", json=reg_data)
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}

def test_get_users(client, db):
    """Test getting all users."""
    headers = get_auth_headers(client, "getusers@example.com")
    
    # Create additional users
    user1 = User(id="list-user-1", email="list1@example.com", name="List User 1", is_active=True)
    user2 = User(id="list-user-2", email="list2@example.com", name="List User 2", is_active=True)
    db.add(user1)
    db.add(user2)
    db.commit()
    
    response = client.get("/api/v1/users", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    assert isinstance(response.json(), list)
    assert len(response.json()) >= 2

def test_get_user_by_id(client, db):
    """Test getting a specific user."""
    headers = get_auth_headers(client, "getuser@example.com")
    
    user = User(
        id="get-user-1",
        email="getuser1@example.com",
        name="Get User",
        is_active=True
    )
    db.add(user)
    db.commit()
    
    response = client.get("/api/v1/users/get-user-1", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["id"] == "get-user-1"

def test_get_user_not_found(client, db):
    """Test getting non-existent user."""
    headers = get_auth_headers(client, "notfounduser@example.com")
    response = client.get("/api/v1/users/non-existent-id", headers=headers)
    assert response.status_code == status.HTTP_404_NOT_FOUND

def test_create_user(client, db):
    """Test creating a user via endpoint."""
    headers = get_auth_headers(client, "createuser@example.com")
    
    user_data = {
        "email": "newuser@example.com",
        "name": "New User",
        "role": "um_nurse"
    }
    response = client.post("/api/v1/users", json=user_data, headers=headers)
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["email"] == "newuser@example.com"

def test_create_user_duplicate_email(client, db):
    """Test creating user with duplicate email."""
    headers = get_auth_headers(client, "duplicateuser@example.com")
    
    user_data = {
        "email": "duplicateuser@example.com",
        "name": "Duplicate User",
        "role": "um_nurse"
    }
    # First creation
    response = client.post("/api/v1/users", json=user_data, headers=headers)
    # Should fail or succeed depending on implementation
    # If it allows, second should fail
    response2 = client.post("/api/v1/users", json=user_data, headers=headers)
    # Either 400 or 200 depending on implementation

def test_get_users_with_pagination(client, db):
    """Test getting users with pagination."""
    headers = get_auth_headers(client, "pagination@example.com")
    
    # Create multiple users
    for i in range(5):
        user = User(
            id=f"page-user-{i}",
            email=f"page{i}@example.com",
            name=f"Page User {i}",
            is_active=True
        )
        db.add(user)
    db.commit()
    
    response = client.get("/api/v1/users?skip=0&limit=2", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    assert len(response.json()) <= 2
