"""Integration tests for NoteRepository"""

import pytest
import uuid
from datetime import datetime, timezone
from app.repositories.note_repository import NoteRepository
from app.models.note import CaseNote
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
        status=CaseStatus.READY,
        priority=Priority.NORMAL,
        uploaded_at=None
    )
    db.add(case)
    db.commit()
    return case


def test_note_repository_create(db, case, user):
    """Test creating a note"""
    repo = NoteRepository()
    
    note = CaseNote(
        id=str(uuid.uuid4()),
        case_id=case.id,
        user_id=user.id,
        author="Test Author",
        text="This is a test note",
        created_at=datetime.now(timezone.utc)
    )
    
    created = repo.create(db, note)
    assert created.id == note.id
    assert created.text == "This is a test note"


def test_note_repository_get_by_case_id(db, case, user):
    """Test getting notes for a case"""
    repo = NoteRepository()
    
    note1 = CaseNote(
        id=str(uuid.uuid4()),
        case_id=case.id,
        user_id=user.id,
        author="Author 1",
        text="Note 1",
        created_at=datetime.now(timezone.utc)
    )
    note2 = CaseNote(
        id=str(uuid.uuid4()),
        case_id=case.id,
        user_id=user.id,
        author="Author 2",
        text="Note 2",
        created_at=datetime.now(timezone.utc)
    )
    db.add(note1)
    db.add(note2)
    db.commit()
    
    # Get ordered (desc)
    notes = repo.get_by_case_id(db, case.id, ordered=True)
    assert len(notes) == 2
    # Verify ordering (newest first)
    assert notes[0].created_at >= notes[1].created_at
    
    # Get unordered
    notes_unordered = repo.get_by_case_id(db, case.id, ordered=False)
    assert len(notes_unordered) == 2


def test_note_repository_get_by_case_id_empty(db, case):
    """Test getting notes for case with no notes"""
    repo = NoteRepository()
    
    notes = repo.get_by_case_id(db, case.id)
    assert len(notes) == 0


def test_note_repository_get_by_case_id_filtered(db, case, user):
    """Test getting notes is filtered by case"""
    repo = NoteRepository()
    
    # Create another case
    case2_id = str(uuid.uuid4())
    case2 = Case(
        id=case2_id,
        user_id=user.id,
        patient_id="PAT-456",
        patient_name="Jane Doe",
        case_number=f"CASE-{uuid.uuid4().hex[:6]}",
        status=CaseStatus.READY,
        priority=Priority.NORMAL,
        uploaded_at=None
    )
    db.add(case2)
    db.commit()
    
    # Create notes for both cases
    note1 = CaseNote(
        id=str(uuid.uuid4()),
        case_id=case.id,
        user_id=user.id,
        author="Author 1",
        text="Note for case 1",
        created_at=datetime.now(timezone.utc)
    )
    note2 = CaseNote(
        id=str(uuid.uuid4()),
        case_id=case2.id,
        user_id=user.id,
        author="Author 2",
        text="Note for case 2",
        created_at=datetime.now(timezone.utc)
    )
    db.add(note1)
    db.add(note2)
    db.commit()
    
    # Get notes for case 1
    notes = repo.get_by_case_id(db, case.id)
    assert len(notes) == 1
    assert notes[0].case_id == case.id


def test_note_repository_delete_by_case_id(db, case, user):
    """Test deleting all notes for a case"""
    repo = NoteRepository()
    
    note1 = CaseNote(
        id=str(uuid.uuid4()),
        case_id=case.id,
        user_id=user.id,
        author="Author 1",
        text="Note 1",
        created_at=datetime.now(timezone.utc)
    )
    note2 = CaseNote(
        id=str(uuid.uuid4()),
        case_id=case.id,
        user_id=user.id,
        author="Author 2",
        text="Note 2",
        created_at=datetime.now(timezone.utc)
    )
    db.add(note1)
    db.add(note2)
    db.commit()
    
    # Delete all notes
    count = repo.delete_by_case_id(db, case.id)
    assert count == 2
    
    # Verify deleted
    notes = repo.get_by_case_id(db, case.id)
    assert len(notes) == 0


def test_note_repository_delete_by_case_id_partial(db, case, user):
    """Test deleting notes doesn't affect other cases"""
    repo = NoteRepository()
    
    # Create another case
    case2_id = str(uuid.uuid4())
    case2 = Case(
        id=case2_id,
        user_id=user.id,
        patient_id="PAT-456",
        patient_name="Jane Doe",
        case_number=f"CASE-{uuid.uuid4().hex[:6]}",
        status=CaseStatus.READY,
        priority=Priority.NORMAL,
        uploaded_at=None
    )
    db.add(case2)
    db.commit()
    
    # Create notes for both cases
    note1 = CaseNote(
        id=str(uuid.uuid4()),
        case_id=case.id,
        user_id=user.id,
        author="Author 1",
        text="Note for case 1",
        created_at=datetime.now(timezone.utc)
    )
    note2 = CaseNote(
        id=str(uuid.uuid4()),
        case_id=case2.id,
        user_id=user.id,
        author="Author 2",
        text="Note for case 2",
        created_at=datetime.now(timezone.utc)
    )
    db.add(note1)
    db.add(note2)
    db.commit()
    
    # Delete notes for case 1
    count = repo.delete_by_case_id(db, case.id)
    assert count == 1
    
    # Verify case 2 notes still exist
    notes2 = repo.get_by_case_id(db, case2.id)
    assert len(notes2) == 1


def test_note_repository_get_by_id(db, case, user):
    """Test getting note by ID"""
    repo = NoteRepository()
    
    note = CaseNote(
        id=str(uuid.uuid4()),
        case_id=case.id,
        user_id=user.id,
        author="Test Author",
        text="Test note",
        created_at=datetime.now(timezone.utc)
    )
    db.add(note)
    db.commit()
    
    found = repo.get_by_id(db, note.id)
    assert found is not None
    assert found.id == note.id


def test_note_repository_update(db, case, user):
    """Test updating a note"""
    repo = NoteRepository()
    
    note = CaseNote(
        id=str(uuid.uuid4()),
        case_id=case.id,
        user_id=user.id,
        author="Test Author",
        text="Original text",
        created_at=datetime.now(timezone.utc)
    )
    db.add(note)
    db.commit()
    
    note.text = "Updated text"
    updated = repo.update(db, note)
    assert updated.text == "Updated text"


def test_note_repository_delete(db, case, user):
    """Test deleting a note"""
    repo = NoteRepository()
    
    note = CaseNote(
        id=str(uuid.uuid4()),
        case_id=case.id,
        user_id=user.id,
        author="Test Author",
        text="Test note",
        created_at=datetime.now(timezone.utc)
    )
    db.add(note)
    db.commit()
    
    repo.delete(db, note.id)
    
    # Verify deleted
    found = repo.get_by_id(db, note.id)
    assert found is None
