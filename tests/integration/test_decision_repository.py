"""Integration tests for DecisionRepository"""

import pytest
import uuid
from datetime import datetime, timezone
from app.repositories.decision_repository import DecisionRepository
from app.models.decision import Decision, DecisionType
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


def test_decision_repository_create(db, case, user):
    """Test creating a decision"""
    repo = DecisionRepository()
    
    decision = Decision(
        id=str(uuid.uuid4()),
        case_id=case.id,
        user_id=user.id,
        decision_type=DecisionType.APPROVED,
        sub_status="standard",
        notes="Test notes",
        decided_by="Test Reviewer",
        decided_at=datetime.now(timezone.utc)
    )
    
    created = repo.create(db, decision)
    assert created.id == decision.id
    assert created.decision_type == DecisionType.APPROVED


def test_decision_repository_get_by_case_id(db, case, user):
    """Test getting decision by case ID"""
    repo = DecisionRepository()
    
    decision = Decision(
        id=str(uuid.uuid4()),
        case_id=case.id,
        user_id=user.id,
        decision_type=DecisionType.APPROVED,
        decided_by="Test Reviewer",
        decided_at=datetime.now(timezone.utc)
    )
    db.add(decision)
    db.commit()
    
    found = repo.get_by_case_id(db, case.id)
    assert found is not None
    assert found.case_id == case.id
    assert found.decision_type == DecisionType.APPROVED


def test_decision_repository_get_by_case_id_not_found(db, case):
    """Test getting decision for case without decision"""
    repo = DecisionRepository()
    
    found = repo.get_by_case_id(db, case.id)
    assert found is None


def test_decision_repository_get_by_decision_type(db, user):
    """Test getting decisions by type"""
    repo = DecisionRepository()
    
    # Create multiple cases and decisions
    case1_id = str(uuid.uuid4())
    case1 = Case(
        id=case1_id,
        user_id=user.id,
        patient_id="PAT-001",
        patient_name="Patient 1",
        case_number=f"CASE-{uuid.uuid4().hex[:6]}",
        status=CaseStatus.READY,
        priority=Priority.NORMAL,
        uploaded_at=None
    )
    
    case2_id = str(uuid.uuid4())
    case2 = Case(
        id=case2_id,
        user_id=user.id,
        patient_id="PAT-002",
        patient_name="Patient 2",
        case_number=f"CASE-{uuid.uuid4().hex[:6]}",
        status=CaseStatus.READY,
        priority=Priority.NORMAL,
        uploaded_at=None
    )
    
    decision1 = Decision(
        id=str(uuid.uuid4()),
        case_id=case1.id,
        user_id=user.id,
        decision_type=DecisionType.APPROVED,
        decided_by="Reviewer 1",
        decided_at=datetime.now(timezone.utc)
    )
    
    decision2 = Decision(
        id=str(uuid.uuid4()),
        case_id=case2.id,
        user_id=user.id,
        decision_type=DecisionType.DENIED,
        decided_by="Reviewer 2",
        decided_at=datetime.now(timezone.utc)
    )
    
    db.add(case1)
    db.add(case2)
    db.add(decision1)
    db.add(decision2)
    db.commit()
    
    # Get approved decisions
    approved = repo.get_by_decision_type(db, DecisionType.APPROVED, skip=0, limit=100)
    assert len(approved) >= 1
    assert all(d.decision_type == DecisionType.APPROVED for d in approved)
    
    # Get denied decisions
    denied = repo.get_by_decision_type(db, DecisionType.DENIED, skip=0, limit=100)
    assert len(denied) >= 1
    assert all(d.decision_type == DecisionType.DENIED for d in denied)


def test_decision_repository_get_by_decision_type_pagination(db, user):
    """Test pagination for get_by_decision_type"""
    repo = DecisionRepository()
    
    # Create multiple decisions
    decisions = []
    for i in range(5):
        case_id = str(uuid.uuid4())
        case = Case(
            id=case_id,
            user_id=user.id,
            patient_id=f"PAT-{i:03d}",
            patient_name=f"Patient {i}",
            case_number=f"CASE-{uuid.uuid4().hex[:6]}",
            status=CaseStatus.READY,
            priority=Priority.NORMAL,
            uploaded_at=None
        )
        decision = Decision(
            id=str(uuid.uuid4()),
            case_id=case.id,
            user_id=user.id,
            decision_type=DecisionType.APPROVED,
            decided_by=f"Reviewer {i}",
            decided_at=datetime.now(timezone.utc)
        )
        db.add(case)
        db.add(decision)
        decisions.append(decision)
    
    db.commit()
    
    # Test pagination
    page1 = repo.get_by_decision_type(db, DecisionType.APPROVED, skip=0, limit=2)
    assert len(page1) == 2
    
    page2 = repo.get_by_decision_type(db, DecisionType.APPROVED, skip=2, limit=2)
    assert len(page2) == 2


def test_decision_repository_get_by_id(db, case, user):
    """Test getting decision by ID"""
    repo = DecisionRepository()
    
    decision = Decision(
        id=str(uuid.uuid4()),
        case_id=case.id,
        user_id=user.id,
        decision_type=DecisionType.APPROVED,
        decided_by="Test Reviewer",
        decided_at=datetime.now(timezone.utc)
    )
    db.add(decision)
    db.commit()
    
    found = repo.get_by_id(db, decision.id)
    assert found is not None
    assert found.id == decision.id


def test_decision_repository_update(db, case, user):
    """Test updating a decision"""
    repo = DecisionRepository()
    
    decision = Decision(
        id=str(uuid.uuid4()),
        case_id=case.id,
        user_id=user.id,
        decision_type=DecisionType.PENDING,
        decided_by="Test Reviewer",
        decided_at=datetime.now(timezone.utc)
    )
    db.add(decision)
    db.commit()
    
    decision.decision_type = DecisionType.APPROVED
    decision.notes = "Updated notes"
    updated = repo.update(db, decision)
    assert updated.decision_type == DecisionType.APPROVED
    assert updated.notes == "Updated notes"


def test_decision_repository_delete(db, case, user):
    """Test deleting a decision"""
    repo = DecisionRepository()
    
    decision = Decision(
        id=str(uuid.uuid4()),
        case_id=case.id,
        user_id=user.id,
        decision_type=DecisionType.APPROVED,
        decided_by="Test Reviewer",
        decided_at=datetime.now(timezone.utc)
    )
    db.add(decision)
    db.commit()
    
    repo.delete(db, decision.id)
    
    # Verify deleted
    found = repo.get_by_id(db, decision.id)
    assert found is None
