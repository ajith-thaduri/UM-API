"""Integration tests for ConversationRepository"""

import pytest
import uuid
from datetime import datetime, timedelta
from app.repositories.conversation_repository import ConversationRepository
from app.models.conversation import ConversationMessage
from app.models.case import Case, CaseStatus, Priority
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


@pytest.fixture
def case(db, user):
    """Create a test case"""
    case_id = str(uuid.uuid4())
    case = Case(
        id=case_id,
        user_id=user.id,
        patient_id="PAT-123",
        patient_name="John Doe",
        case_number=f"CASE-{uuid.uuid4().hex[:6]}",
        status=CaseStatus.UPLOADED,
        priority=Priority.NORMAL,
        uploaded_at=None
    )
    db.add(case)
    db.commit()
    return case


def test_conversation_repository_add_message(db, case, user):
    """Test adding a message to conversation"""
    repo = ConversationRepository()
    
    message = repo.add_message(
        db=db,
        case_id=case.id,
        user_id=user.id,
        role="user",
        content="Hello, what is the patient's diagnosis?",
        sources=None
    )
    
    assert message.id is not None
    assert message.case_id == case.id
    assert message.user_id == user.id
    assert message.role == "user"
    assert message.content == "Hello, what is the patient's diagnosis?"
    assert message.sources == []


def test_conversation_repository_add_message_with_sources(db, case, user):
    """Test adding a message with sources"""
    repo = ConversationRepository()
    
    sources = [
        {"chunk_id": "chunk-1", "file_id": "file-1", "page_number": 1}
    ]
    
    message = repo.add_message(
        db=db,
        case_id=case.id,
        user_id=user.id,
        role="assistant",
        content="The patient has diabetes.",
        sources=sources
    )
    
    assert message.sources == sources


def test_conversation_repository_get_conversation_history(db, case, user):
    """Test getting conversation history"""
    repo = ConversationRepository()
    
    # Add multiple messages
    message1 = repo.add_message(
        db=db,
        case_id=case.id,
        user_id=user.id,
        role="user",
        content="Question 1"
    )
    
    # Small delay to ensure different timestamps
    import time
    time.sleep(0.01)
    
    message2 = repo.add_message(
        db=db,
        case_id=case.id,
        user_id=user.id,
        role="assistant",
        content="Answer 1"
    )
    
    time.sleep(0.01)
    
    message3 = repo.add_message(
        db=db,
        case_id=case.id,
        user_id=user.id,
        role="user",
        content="Question 2"
    )
    
    # Get conversation history
    history = repo.get_conversation_history(db, case.id, user.id, limit=10)
    
    assert len(history) == 3
    # Verify ordering (oldest first)
    assert history[0].created_at <= history[1].created_at
    assert history[1].created_at <= history[2].created_at


def test_conversation_repository_get_conversation_history_with_limit(db, case, user):
    """Test getting conversation history with limit"""
    repo = ConversationRepository()
    
    # Add 5 messages
    for i in range(5):
        repo.add_message(
            db=db,
            case_id=case.id,
            user_id=user.id,
            role="user" if i % 2 == 0 else "assistant",
            content=f"Message {i}"
        )
        import time
        time.sleep(0.01)
    
    # Get with limit
    history = repo.get_conversation_history(db, case.id, user.id, limit=3)
    assert len(history) == 3


def test_conversation_repository_get_conversation_history_filtered(db, case, user):
    """Test conversation history is filtered by case and user"""
    repo = ConversationRepository()
    
    # Create another user and case
    user2_id = str(uuid.uuid4())
    user2 = User(
        id=user2_id,
        email=f"user2-{user2_id[:8]}@example.com",
        name="Test User 2",
        is_active=True
    )
    case2_id = str(uuid.uuid4())
    case2 = Case(
        id=case2_id,
        user_id=user2.id,
        patient_id="PAT-456",
        patient_name="Jane Doe",
        case_number=f"CASE-{uuid.uuid4().hex[:6]}",
        status=CaseStatus.UPLOADED,
        priority=Priority.NORMAL,
        uploaded_at=None
    )
    db.add(user2)
    db.add(case2)
    db.commit()
    
    # Add messages for both cases/users
    repo.add_message(db, case.id, user.id, "user", "Message for case 1")
    repo.add_message(db, case2.id, user2.id, "user", "Message for case 2")
    repo.add_message(db, case.id, user.id, "assistant", "Response for case 1")
    
    # Get history for case 1, user 1
    history = repo.get_conversation_history(db, case.id, user.id, limit=10)
    assert len(history) == 2
    assert all(msg.case_id == case.id and msg.user_id == user.id for msg in history)


def test_conversation_repository_clear_conversation(db, case, user):
    """Test clearing conversation"""
    repo = ConversationRepository()
    
    # Add multiple messages
    repo.add_message(db, case.id, user.id, "user", "Message 1")
    repo.add_message(db, case.id, user.id, "assistant", "Response 1")
    repo.add_message(db, case.id, user.id, "user", "Message 2")
    
    # Clear conversation
    count = repo.clear_conversation(db, case.id, user.id)
    assert count == 3
    
    # Verify cleared
    history = repo.get_conversation_history(db, case.id, user.id, limit=10)
    assert len(history) == 0


def test_conversation_repository_clear_conversation_partial(db, case, user):
    """Test clearing conversation doesn't affect other conversations"""
    repo = ConversationRepository()
    
    # Create another case
    case2_id = str(uuid.uuid4())
    case2 = Case(
        id=case2_id,
        user_id=user.id,
        patient_id="PAT-456",
        patient_name="Jane Doe",
        case_number=f"CASE-{uuid.uuid4().hex[:6]}",
        status=CaseStatus.UPLOADED,
        priority=Priority.NORMAL,
        uploaded_at=None
    )
    db.add(case2)
    db.commit()
    
    # Add messages for both cases
    repo.add_message(db, case.id, user.id, "user", "Message for case 1")
    repo.add_message(db, case2.id, user.id, "user", "Message for case 2")
    
    # Clear conversation for case 1 only
    count = repo.clear_conversation(db, case.id, user.id)
    assert count == 1
    
    # Verify case 2 messages still exist
    history2 = repo.get_conversation_history(db, case2.id, user.id, limit=10)
    assert len(history2) == 1
