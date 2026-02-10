"""Integration tests for EvidenceClickRepository"""

import pytest
import uuid
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.repositories.evidence_click_repository import EvidenceClickRepository
from app.models.evidence_click import EvidenceClick
from app.models.case import Case, CaseStatus, Priority
from app.models.user import User
from app.db.session import SessionLocal


@pytest.fixture
def db():
    """Database session for testing"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.rollback()
        db.close()


@pytest.fixture
def user(db):
    """Create a test user"""
    user = User(
        id=str(uuid.uuid4()),
        email=f"test-{uuid.uuid4()}@example.com",
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
        patient_id="PID-123",
        patient_name="John Doe",
        case_number=f"CASE-{uuid.uuid4().hex[:6]}",
        status=CaseStatus.UPLOADED,
        priority=Priority.NORMAL,
        uploaded_at=datetime.utcnow()
    )
    db.add(case)
    db.commit()
    return case


@pytest.fixture
def case2(db, user):
    """Create a second test case"""
    case_id = str(uuid.uuid4())
    case = Case(
        id=case_id,
        user_id=user.id,
        patient_id="PID-456",
        patient_name="Jane Doe",
        case_number=f"CASE-{uuid.uuid4().hex[:6]}",
        status=CaseStatus.UPLOADED,
        priority=Priority.NORMAL,
        uploaded_at=datetime.utcnow()
    )
    db.add(case)
    db.commit()
    return case


@pytest.fixture
def evidence_click_repo():
    return EvidenceClickRepository()


def test_create_evidence_click(evidence_click_repo, db, case, user):
    """Test creating an evidence click"""
    click_id = str(uuid.uuid4())
    click = EvidenceClick(
        id=click_id,
        user_id=user.id,
        case_id=case.id,
        entity_type="medication",
        entity_id="medication:0",
        source_type="file",
        file_id="file-1",
        page_number=1
    )
    
    result = evidence_click_repo.create(db, click)
    
    assert result.id == click_id
    assert result.user_id == user.id
    assert result.case_id == case.id
    db.commit()


def test_get_by_case(evidence_click_repo, db, case, case2, user):
    """Test getting clicks for a specific case"""
    # Create multiple clicks for case-1
    for i in range(3):
        click = EvidenceClick(
            id=str(uuid.uuid4()),
            user_id=user.id,
            case_id=case.id,
            entity_type="medication",
            entity_id=f"medication:{i}",
            source_type="file",
            file_id="file-1",
            page_number=i + 1
        )
        evidence_click_repo.create(db, click)
    
    # Create click for different case
    other_click = EvidenceClick(
        id=str(uuid.uuid4()),
        user_id=user.id,
        case_id=case2.id,
        entity_type="medication",
        entity_id="medication:0",
        source_type="file",
        file_id="file-1",
        page_number=1
    )
    evidence_click_repo.create(db, other_click)
    db.commit()
    
    results = evidence_click_repo.get_by_case(db, case.id, user.id)
    
    assert len(results) == 3
    assert all(r.case_id == case.id for r in results)


def test_get_counts_by_type(evidence_click_repo, db, case, user):
    """Test getting click counts by entity type"""
    # Create clicks of different types
    types = ["medication", "lab", "medication", "diagnosis", "medication"]
    for i, entity_type in enumerate(types):
        click = EvidenceClick(
            id=str(uuid.uuid4()),
            user_id=user.id,
            case_id=case.id,
            entity_type=entity_type,
            entity_id=f"{entity_type}:{i}",
            source_type="file",
            file_id="file-1",
            page_number=1
        )
        evidence_click_repo.create(db, click)
    
    db.commit()
    
    counts = evidence_click_repo.get_counts_by_type(db, user.id)
    
    assert counts["medication"] == 3
    assert counts["lab"] == 1
    assert counts["diagnosis"] == 1


def test_get_counts_by_type_with_date_filter(evidence_click_repo, db, case, user):
    """Test getting click counts with date filtering"""
    now = datetime.utcnow()
    
    # Create clicks at different times
    for i in range(3):
        click = EvidenceClick(
            id=str(uuid.uuid4()),
            user_id=user.id,
            case_id=case.id,
            entity_type="medication",
            entity_id=f"medication:{i}",
            source_type="file",
            file_id="file-1",
            page_number=1,
            clicked_at=now - timedelta(days=i)
        )
        evidence_click_repo.create(db, click)
    
    db.commit()
    
    # Get counts for last 2 days (should include clicks from days 0, 1, 2)
    start_date = now - timedelta(days=2)
    counts = evidence_click_repo.get_counts_by_type(
        db, user.id, start_date=start_date
    )
    
    # All 3 clicks are within the last 2 days (days 0, 1, 2)
    assert counts.get("medication", 0) >= 2


def test_get_clicks_by_case(evidence_click_repo, db, case, case2, user):
    """Test getting click counts grouped by case"""
    # Create clicks for multiple cases
    case_ids = [case.id, case.id, case2.id, case.id]
    for i, case_id in enumerate(case_ids):
        click = EvidenceClick(
            id=str(uuid.uuid4()),
            user_id=user.id,
            case_id=case_id,
            entity_type="medication",
            entity_id=f"medication:{i}",
            source_type="file",
            file_id="file-1",
            page_number=1
        )
        evidence_click_repo.create(db, click)
    
    db.commit()
    
    results = evidence_click_repo.get_clicks_by_case(db, user.id)
    
    # Should be sorted by click count descending
    assert len(results) == 2
    assert results[0]["case_id"] == case.id
    assert results[0]["clicks"] == 3
    assert results[1]["case_id"] == case2.id
    assert results[1]["clicks"] == 1


def test_get_time_series(evidence_click_repo, db, case, user):
    """Test getting time-series data for clicks"""
    now = datetime.utcnow()
    
    # Create clicks on different days
    for i in range(5):
        click = EvidenceClick(
            id=str(uuid.uuid4()),
            user_id=user.id,
            case_id=case.id,
            entity_type="medication",
            entity_id=f"medication:{i}",
            source_type="file",
            file_id="file-1",
            page_number=1,
            clicked_at=now - timedelta(days=i)
        )
        evidence_click_repo.create(db, click)
    
    db.commit()
    
    start_date = now - timedelta(days=7)
    end_date = now
    
    results = evidence_click_repo.get_time_series(
        db, user.id, start_date, end_date, group_by="day"
    )
    
    assert len(results) >= 1
    assert all("date" in r for r in results)
    assert all("clicks" in r for r in results)


def test_get_recent_clicks(evidence_click_repo, db, case, user):
    """Test getting recent clicks for a user"""
    now = datetime.utcnow()
    
    # Create clicks at different times
    for i in range(5):
        click = EvidenceClick(
            id=str(uuid.uuid4()),
            user_id=user.id,
            case_id=case.id,
            entity_type="medication",
            entity_id=f"medication:{i}",
            source_type="file",
            file_id="file-1",
            page_number=1,
            clicked_at=now - timedelta(minutes=i)
        )
        evidence_click_repo.create(db, click)
    
    db.commit()
    
    results = evidence_click_repo.get_recent_clicks(db, user.id, limit=3)
    
    assert len(results) == 3
    # Should be ordered by clicked_at descending (most recent first)
    assert results[0].clicked_at >= results[1].clicked_at
    assert results[1].clicked_at >= results[2].clicked_at
