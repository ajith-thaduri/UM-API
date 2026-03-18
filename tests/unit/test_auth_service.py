import pytest
from unittest.mock import MagicMock, patch
from sqlalchemy.orm import Session
from app.services import auth_service
from app.models.user import User
from datetime import timedelta

@pytest.fixture
def mock_db():
    return MagicMock(spec=Session)

def test_password_hashing():
    password = "testpassword"
    hashed = auth_service.get_password_hash(password)
    assert hashed != password
    assert auth_service.verify_password(password, hashed) is True
    assert auth_service.verify_password("wrong", hashed) is False

def test_create_access_token():
    data = {"sub": "user-1"}
    token = auth_service.create_access_token(data)
    assert isinstance(token, str)
    assert len(token) > 0

def test_authenticate_user_success(mock_db):
    user = User(email="test@example.com", hashed_password=auth_service.get_password_hash("password"), is_active=True)
    
    with patch("app.services.auth_service.user_repository.get_by_email", return_value=user):
        authenticated_user = auth_service.authenticate_user(mock_db, "test@example.com", "password")
        assert authenticated_user == user
        assert mock_db.commit.called

def test_authenticate_user_failure(mock_db):
    with patch("app.services.auth_service.user_repository.get_by_email", return_value=None):
        assert auth_service.authenticate_user(mock_db, "wrong@example.com", "password") is None

def test_get_user_from_token_success(mock_db):
    token = auth_service.create_access_token({"sub": "user-1"})
    user = User(id="user-1", is_active=True)
    
    with patch("app.services.auth_service.token_blacklist_repository.is_blacklisted", return_value=False), \
         patch("app.services.auth_service.user_repository.get_by_id", return_value=user):
        
        result = auth_service.get_user_from_token(token, mock_db)
        assert result == user
