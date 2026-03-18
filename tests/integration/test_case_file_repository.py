"""Integration tests for CaseFileRepository"""

import pytest
import uuid
from app.repositories.case_file_repository import CaseFileRepository
from app.models.case_file import CaseFile
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


def test_case_file_repository_get_by_case_id(db, case, user):
    """Test getting all files for a case"""
    repo = CaseFileRepository()
    
    # Create multiple files
    file1 = CaseFile(
        id=str(uuid.uuid4()),
        case_id=case.id,
        user_id=user.id,
        file_name="file1.pdf",
        file_path="/path/to/file1.pdf",
        file_size=1024,
        page_count=5,
        file_order=0
    )
    file2 = CaseFile(
        id=str(uuid.uuid4()),
        case_id=case.id,
        user_id=user.id,
        file_name="file2.pdf",
        file_path="/path/to/file2.pdf",
        file_size=2048,
        page_count=10,
        file_order=1
    )
    db.add(file1)
    db.add(file2)
    db.commit()
    
    # Get files ordered
    files = repo.get_by_case_id(db, case.id, ordered=True)
    assert len(files) == 2
    assert files[0].file_order == 0
    assert files[1].file_order == 1
    
    # Get files unordered
    files_unordered = repo.get_by_case_id(db, case.id, ordered=False)
    assert len(files_unordered) == 2


def test_case_file_repository_get_by_case_and_file_id(db, case, user):
    """Test getting specific file by case and file ID"""
    repo = CaseFileRepository()
    
    file = CaseFile(
        id=str(uuid.uuid4()),
        case_id=case.id,
        user_id=user.id,
        file_name="test.pdf",
        file_path="/path/to/test.pdf",
        file_size=1024,
        page_count=5,
        file_order=0
    )
    db.add(file)
    db.commit()
    
    found = repo.get_by_case_and_file_id(db, case.id, file.id)
    assert found is not None
    assert found.id == file.id
    assert found.case_id == case.id
    
    # Test non-existent file
    non_existent = repo.get_by_case_and_file_id(db, case.id, "non-existent-id")
    assert non_existent is None


def test_case_file_repository_delete_by_case_id(db, case, user):
    """Test deleting all files for a case"""
    repo = CaseFileRepository()
    
    # Create multiple files
    file1 = CaseFile(
        id=str(uuid.uuid4()),
        case_id=case.id,
        user_id=user.id,
        file_name="file1.pdf",
        file_path="/path/to/file1.pdf",
        file_size=1024,
        page_count=5,
        file_order=0
    )
    file2 = CaseFile(
        id=str(uuid.uuid4()),
        case_id=case.id,
        user_id=user.id,
        file_name="file2.pdf",
        file_path="/path/to/file2.pdf",
        file_size=2048,
        page_count=10,
        file_order=1
    )
    db.add(file1)
    db.add(file2)
    db.commit()
    
    # Delete all files
    count = repo.delete_by_case_id(db, case.id)
    assert count == 2
    
    # Verify deleted
    files = repo.get_by_case_id(db, case.id)
    assert len(files) == 0


def test_case_file_repository_create(db, case, user):
    """Test creating a case file"""
    repo = CaseFileRepository()
    
    file = CaseFile(
        id=str(uuid.uuid4()),
        case_id=case.id,
        user_id=user.id,
        file_name="new_file.pdf",
        file_path="/path/to/new_file.pdf",
        file_size=1024,
        page_count=5,
        file_order=0
    )
    
    created = repo.create(db, file)
    assert created.id == file.id
    assert created.file_name == "new_file.pdf"


def test_case_file_repository_get_by_id(db, case, user):
    """Test getting case file by ID"""
    repo = CaseFileRepository()
    
    file = CaseFile(
        id=str(uuid.uuid4()),
        case_id=case.id,
        user_id=user.id,
        file_name="test.pdf",
        file_path="/path/to/test.pdf",
        file_size=1024,
        page_count=5,
        file_order=0
    )
    db.add(file)
    db.commit()
    
    found = repo.get_by_id(db, file.id)
    assert found is not None
    assert found.id == file.id


def test_case_file_repository_update(db, case, user):
    """Test updating a case file"""
    repo = CaseFileRepository()
    
    file = CaseFile(
        id=str(uuid.uuid4()),
        case_id=case.id,
        user_id=user.id,
        file_name="test.pdf",
        file_path="/path/to/test.pdf",
        file_size=1024,
        page_count=5,
        file_order=0
    )
    db.add(file)
    db.commit()
    
    file.file_name = "updated.pdf"
    updated = repo.update(db, file)
    assert updated.file_name == "updated.pdf"


def test_case_file_repository_delete(db, case, user):
    """Test deleting a case file"""
    repo = CaseFileRepository()
    
    file = CaseFile(
        id=str(uuid.uuid4()),
        case_id=case.id,
        user_id=user.id,
        file_name="test.pdf",
        file_path="/path/to/test.pdf",
        file_size=1024,
        page_count=5,
        file_order=0
    )
    db.add(file)
    db.commit()
    
    repo.delete(db, file.id)
    
    # Verify deleted
    found = repo.get_by_id(db, file.id)
    assert found is None
