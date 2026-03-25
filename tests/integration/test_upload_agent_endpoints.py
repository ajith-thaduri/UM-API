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


@patch("app.api.endpoints.upload_agent.delete_temp_upload_storage")
def test_delete_session_invokes_temp_storage_cleanup(mock_cleanup, client, db):
    headers = get_auth_headers(client, "deletesess@example.com")
    user = db.query(User).filter(User.email == "deletesess@example.com").first()
    session_id = str(uuid.uuid4())
    session = UploadSession(
        id=session_id,
        user_id=user.id,
        state="waiting_for_files",
        patient_info={},
        messages=[],
        files=[],
    )
    db.add(session)
    db.commit()

    response = client.delete(f"/api/v1/upload/agent/session/{session_id}", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    mock_cleanup.assert_called_once()
    assert mock_cleanup.call_args.kwargs["user_id"] == user.id
    assert mock_cleanup.call_args.kwargs["session_id"] == session_id


@patch(
    "app.api.endpoints.upload_agent.delete_temp_upload_storage",
    side_effect=RuntimeError("storage unavailable"),
)
def test_delete_session_still_removes_row_when_storage_fails(mock_cleanup, client, db):
    headers = get_auth_headers(client, "deletesessfail@example.com")
    user = db.query(User).filter(User.email == "deletesessfail@example.com").first()
    session_id = str(uuid.uuid4())
    db.add(
        UploadSession(
            id=session_id,
            user_id=user.id,
            state="greeting",
            patient_info={},
            messages=[],
            files=[],
        )
    )
    db.commit()

    response = client.delete(f"/api/v1/upload/agent/session/{session_id}", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    remaining = db.query(UploadSession).filter(UploadSession.id == session_id).first()
    assert remaining is None


def test_list_upload_sessions_only_resumable_without_case(client, db):
    headers = get_auth_headers(client, "listsess@example.com")
    user = db.query(User).filter(User.email == "listsess@example.com").first()
    s1, s2, s3 = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
    db.add(
        UploadSession(
            id=s1,
            user_id=user.id,
            state="waiting_for_files",
            patient_info={},
            messages=[],
            files=[{"name": "a.pdf"}],
        )
    )
    db.add(
        UploadSession(
            id=s2,
            user_id=user.id,
            state="processing",
            patient_info={},
            messages=[],
            files=[],
        )
    )
    db.add(
        UploadSession(
            id=s3,
            user_id=user.id,
            state="greeting",
            patient_info={},
            messages=[],
            files=[],
            case_id="linked-case-1",
        )
    )
    db.commit()

    response = client.get("/api/v1/upload/agent/sessions", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    payload = response.json()
    ids = {row["session_id"] for row in payload}
    assert s1 in ids
    assert s2 not in ids
    assert s3 not in ids
    draft = next(r for r in payload if r["session_id"] == s1)
    assert draft["file_count"] == 1


def test_list_upload_sessions_excludes_zero_file_drafts(client, db):
    """Drafts without uploaded files are not listed (avoids clutter; client does not persist until PDF)."""
    headers = get_auth_headers(client, "listzerofile@example.com")
    user = db.query(User).filter(User.email == "listzerofile@example.com").first()
    with_files = str(uuid.uuid4())
    no_files = str(uuid.uuid4())
    db.add(
        UploadSession(
            id=with_files,
            user_id=user.id,
            state="waiting_for_files",
            patient_info={},
            messages=[],
            files=[{"name": "x.pdf"}],
        )
    )
    db.add(
        UploadSession(
            id=no_files,
            user_id=user.id,
            state="waiting_for_files",
            patient_info={},
            messages=[],
            files=[],
        )
    )
    db.commit()

    response = client.get("/api/v1/upload/agent/sessions", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    ids = {row["session_id"] for row in response.json()}
    assert with_files in ids
    assert no_files not in ids


def test_resume_upload_session_ok(client, db):
    headers = get_auth_headers(client, "resumeok@example.com")
    user = db.query(User).filter(User.email == "resumeok@example.com").first()
    session_id = str(uuid.uuid4())
    db.add(
        UploadSession(
            id=session_id,
            user_id=user.id,
            state="review_summary",
            patient_info={"name": "Patient A"},
            messages=[{"role": "agent", "id": "m1", "message": "hi"}],
            files=[
                {
                    "name": "doc.pdf",
                    "pages": 3,
                    "type": "clinical",
                    "temp_path": "users/u/cases/temp_x/f.pdf",
                }
            ],
        )
    )
    db.commit()

    response = client.post(f"/api/v1/upload/agent/resume/{session_id}", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["session_id"] == session_id
    assert data["state"] == "review_summary"
    assert data["patient_info"]["name"] == "Patient A"
    assert len(data["messages"]) == 1
    assert data.get("file_count") == 1
    assert len(data.get("files") or []) == 1
    assert data["files"][0]["name"] == "doc.pdf"
    assert data["files"][0]["pages"] == 3


def test_get_upload_session_file_requires_storage_path(client, db):
    """Vault download returns 404 when session row has no resolvable path."""
    headers = get_auth_headers(client, "vaultdl@example.com")
    user = db.query(User).filter(User.email == "vaultdl@example.com").first()
    session_id = str(uuid.uuid4())
    db.add(
        UploadSession(
            id=session_id,
            user_id=user.id,
            state="collecting_data",
            patient_info={},
            messages=[],
            files=[{"name": "orphan.pdf", "pages": 1, "type": "unknown"}],
        )
    )
    db.commit()

    response = client.get(
        f"/api/v1/upload/agent/session/{session_id}/file/0",
        headers=headers,
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_resume_rejects_non_resumable_state(client, db):
    headers = get_auth_headers(client, "resumenope@example.com")
    user = db.query(User).filter(User.email == "resumenope@example.com").first()
    session_id = str(uuid.uuid4())
    db.add(
        UploadSession(
            id=session_id,
            user_id=user.id,
            state="processing",
            patient_info={},
            messages=[],
            files=[],
        )
    )
    db.commit()

    response = client.post(f"/api/v1/upload/agent/resume/{session_id}", headers=headers)
    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_resume_forbidden_wrong_user(client, db):
    headers_a = get_auth_headers(client, "resumeusera@example.com")
    get_auth_headers(client, "resumeuserb@example.com")
    user_b = db.query(User).filter(User.email == "resumeuserb@example.com").first()
    session_id = str(uuid.uuid4())
    db.add(
        UploadSession(
            id=session_id,
            user_id=user_b.id,
            state="collecting_data",
            patient_info={},
            messages=[],
            files=[],
        )
    )
    db.commit()

    response = client.post(f"/api/v1/upload/agent/resume/{session_id}", headers=headers_a)
    assert response.status_code == status.HTTP_403_FORBIDDEN
