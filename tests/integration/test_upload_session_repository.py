"""Integration tests for UploadSessionRepository"""

import pytest
import uuid
from app.repositories.upload_session_repository import UploadSessionRepository
from app.models.upload_session import UploadSession
from app.models.user import User


@pytest.fixture
def user(db):
    """Create a test user"""
    user_id = str(uuid.uuid4())
    user = User(
        id=user_id,
        email=f"user-{user_id[:8]}@example.com",
        name="Test User",
        is_active=True
    )
    db.add(user)
    db.commit()
    return user


def test_upload_session_repository_create(db, user):
    """Test creating an upload session"""
    repo = UploadSessionRepository()
    
    session = UploadSession(
        id=str(uuid.uuid4()),
        user_id=user.id,
        state="greeting",
        patient_info={"name": "John Doe"},
        case_number=None,
        priority="normal"
    )
    
    created = repo.create(db, session)
    assert created.id == session.id
    assert created.user_id == user.id


def test_upload_session_repository_get_by_id(db, user):
    """Test getting session by ID"""
    repo = UploadSessionRepository()
    
    session = UploadSession(
        id=str(uuid.uuid4()),
        user_id=user.id,
        state="greeting",
        patient_info={"name": "John Doe"},
        case_number=None,
        priority="normal"
    )
    db.add(session)
    db.commit()
    
    found = repo.get_by_id(db, session.id)
    assert found is not None
    assert found.id == session.id
    assert found.user_id == user.id


def test_upload_session_repository_get_by_id_not_found(db):
    """Test getting non-existent session"""
    repo = UploadSessionRepository()
    
    found = repo.get_by_id(db, "non-existent-id")
    assert found is None


def test_upload_session_repository_get_by_user(db, user):
    """Test getting all sessions for a user"""
    repo = UploadSessionRepository()
    
    session1 = UploadSession(
        id=str(uuid.uuid4()),
        user_id=user.id,
        state="greeting",
        patient_info={"name": "John Doe"},
        case_number=None,
        priority="normal"
    )
    session2 = UploadSession(
        id=str(uuid.uuid4()),
        user_id=user.id,
        state="collecting_info",
        patient_info={"name": "Jane Doe"},
        case_number=None,
        priority="high"
    )
    
    # Create another user with sessions
    user2_id = str(uuid.uuid4())
    user2 = User(
        id=user2_id,
        email=f"user2-{user2_id[:8]}@example.com",
        name="Test User 2",
        is_active=True
    )
    db.add(user2)
    db.commit()
    
    session3 = UploadSession(
        id=str(uuid.uuid4()),
        user_id=user2.id,
        state="greeting",
        patient_info={"name": "Bob Smith"},
        case_number=None,
        priority="normal"
    )
    
    db.add(session1)
    db.add(session2)
    db.add(session3)
    db.commit()
    
    # Get sessions for user 1
    sessions = repo.get_by_user(db, user.id)
    assert len(sessions) == 2
    assert all(s.user_id == user.id for s in sessions)


def test_upload_session_repository_get_by_user_empty(db, user):
    """Test getting sessions for user with no sessions"""
    repo = UploadSessionRepository()
    
    sessions = repo.get_by_user(db, user.id)
    assert len(sessions) == 0


def test_upload_session_repository_delete_by_id(db, user):
    """Test deleting session by ID"""
    repo = UploadSessionRepository()
    
    session = UploadSession(
        id=str(uuid.uuid4()),
        user_id=user.id,
        state="greeting",
        patient_info={"name": "John Doe"},
        case_number=None,
        priority="normal"
    )
    db.add(session)
    db.commit()
    
    result = repo.delete_by_id(db, session.id)
    assert result is True
    
    # Verify deleted
    found = repo.get_by_id(db, session.id)
    assert found is None


def test_upload_session_repository_delete_by_id_not_found(db):
    """Test deleting non-existent session"""
    repo = UploadSessionRepository()
    
    result = repo.delete_by_id(db, "non-existent-id")
    assert result is False


def test_upload_session_repository_update(db, user):
    """Test updating a session"""
    repo = UploadSessionRepository()
    
    session = UploadSession(
        id=str(uuid.uuid4()),
        user_id=user.id,
        state="greeting",
        patient_info={"name": "John Doe"},
        case_number=None,
        priority="normal"
    )
    db.add(session)
    db.commit()
    
    session.state = "collecting_info"
    session.case_number = "CASE-123"
    updated = repo.update(db, session)
    assert updated.state == "collecting_info"
    assert updated.case_number == "CASE-123"
