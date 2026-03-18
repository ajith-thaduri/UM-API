"""Integration tests for Upload Agent API endpoints"""

import pytest
import uuid
from datetime import datetime
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi import status
from app.models.user import User
from app.models.upload_session import UploadSession


def get_auth_headers(client, email="uploadagent@example.com", password="password123"):
    """Helper to register and get auth token."""
    reg_data = {"email": email, "password": password, "name": "Test User"}
    response = client.post("/api/v1/auth/register", json=reg_data)
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@patch("app.services.upload_agent_service.upload_agent_service.start_session")
def test_start_session(mock_start_session, client, db):
    """Test starting an upload session"""
    headers = get_auth_headers(client, "startsession@example.com")
    
    user = db.query(User).filter(User.email == "startsession@example.com").first()
    
    session_id = str(uuid.uuid4())
    from app.services.upload_agent_service import AgentMessage
    greeting = AgentMessage(
        id="msg-1",
        message="Hello! Welcome to the upload assistant.",
        type="greeting",
        timestamp=datetime.utcnow().isoformat(),
        actions=[],
        current_field=None,
        suggestions=[],
        extracted_data=None,
        files_info=None,
        progress=0
    )
    
    mock_start_session.return_value = (session_id, greeting)
    
    response = client.post("/api/v1/upload/agent/start", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "session_id" in data
    assert "message" in data


def test_get_session_messages(client, db):
    """Test getting session messages"""
    headers = get_auth_headers(client, "sessionmessages@example.com")
    
    user = db.query(User).filter(User.email == "sessionmessages@example.com").first()
    
    session_id = str(uuid.uuid4())
    session = UploadSession(
        id=session_id,
        user_id=user.id,
        state="collecting_info",
        patient_info={"name": "John Doe"},
        messages=[{"role": "agent", "content": "Hello"}]
    )
    db.add(session)
    db.commit()
    
    # Correct route: /api/v1/upload/agent/messages/{session_id}
    response = client.get(f"/api/v1/upload/agent/messages/{session_id}", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["session_id"] == session_id
    assert "messages" in data


def test_get_session_not_found(client, db):
    """Test getting non-existent session"""
    headers = get_auth_headers(client, "nosession@example.com")
    
    response = client.get("/api/v1/upload/agent/non-existent-id/status", headers=headers)
    assert response.status_code == status.HTTP_404_NOT_FOUND
