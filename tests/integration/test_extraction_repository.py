import pytest
from app.repositories.extraction_repository import ExtractionRepository
from app.models.extraction import ClinicalExtraction
from app.models.case import Case, CaseStatus, Priority
from app.models.user import User

def test_extraction_repository_get_by_case_id(db):
    """Test getting extraction by case ID."""
    repo = ExtractionRepository()
    
    user = User(
        id="extraction-repo-user-1",
        email="extractionrepo1@example.com",
        name="Extraction Repo User",
        is_active=True
    )
    case = Case(
        id="extraction-repo-case-1",
        patient_id="PAT-REPO-1",
        patient_name="Repo Patient",
        case_number="CASE-REPO-1",
        status=CaseStatus.READY,
        priority=Priority.NORMAL,
        user_id=user.id
    )
    extraction = ClinicalExtraction(
        id="extraction-repo-1",
        case_id=case.id,
        user_id=user.id,
        extracted_data={"test": "data"}
    )
    db.add(user)
    db.add(case)
    db.add(extraction)
    db.commit()
    
    found = repo.get_by_case_id(db, case.id)
    assert found is not None
    assert found.case_id == case.id

def test_extraction_repository_get_by_case_id_with_user_filter(db):
    """Test getting extraction with user filter."""
    repo = ExtractionRepository()
    
    user1 = User(
        id="extraction-user-1",
        email="extractionuser1@example.com",
        name="Extraction User 1",
        is_active=True
    )
    user2 = User(
        id="extraction-user-2",
        email="extractionuser2@example.com",
        name="Extraction User 2",
        is_active=True
    )
    case = Case(
        id="extraction-filter-case-1",
        patient_id="PAT-FILTER-1",
        patient_name="Filter Patient",
        case_number="CASE-FILTER-1",
        status=CaseStatus.READY,
        priority=Priority.NORMAL,
        user_id=user1.id
    )
    extraction = ClinicalExtraction(
        id="extraction-filter-1",
        case_id=case.id,
        user_id=user1.id,
        extracted_data={"test": "data"}
    )
    db.add(user1)
    db.add(user2)
    db.add(case)
    db.add(extraction)
    db.commit()
    
    # Should find with correct user
    found = repo.get_by_case_id(db, case.id, user_id=user1.id)
    assert found is not None
    
    # Should not find with wrong user
    found_wrong = repo.get_by_case_id(db, case.id, user_id=user2.id)
    assert found_wrong is None

def test_extraction_repository_delete_by_case_id(db):
    """Test deleting extraction by case ID."""
    repo = ExtractionRepository()
    
    user = User(
        id="delete-extraction-user-1",
        email="deleteextraction1@example.com",
        name="Delete Extraction User",
        is_active=True
    )
    case = Case(
        id="delete-extraction-case-1",
        patient_id="PAT-DELETE-1",
        patient_name="Delete Patient",
        case_number="CASE-DELETE-1",
        status=CaseStatus.READY,
        priority=Priority.NORMAL,
        user_id=user.id
    )
    extraction = ClinicalExtraction(
        id="delete-extraction-1",
        case_id=case.id,
        user_id=user.id,
        extracted_data={"test": "data"}
    )
    db.add(user)
    db.add(case)
    db.add(extraction)
    db.commit()
    
    result = repo.delete_by_case_id(db, case.id)
    assert result is True
    
    # Verify deleted
    found = repo.get_by_case_id(db, case.id)
    assert found is None

def test_extraction_repository_delete_by_case_id_not_found(db):
    """Test deleting non-existent extraction."""
    repo = ExtractionRepository()
    result = repo.delete_by_case_id(db, "non-existent-case")
    assert result is False
