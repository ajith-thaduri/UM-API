"""Integration tests for FacetRepository"""

import pytest
import uuid
from app.repositories.facet_repository import FacetRepository
from app.models.dashboard import FacetResult, FacetType, FacetStatus, DashboardSnapshot
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


@pytest.fixture
def snapshot(db, case, user):
    """Create a test dashboard snapshot"""
    snapshot = DashboardSnapshot(
        id=str(uuid.uuid4()),
        case_id=case.id,
        user_id=user.id,
        version=1,
        status=FacetStatus.READY
    )
    db.add(snapshot)
    db.commit()
    return snapshot


def test_facet_repository_create(db, snapshot, case, user):
    """Test creating a facet result"""
    repo = FacetRepository()
    
    facet = FacetResult(
        id=str(uuid.uuid4()),
        snapshot_id=snapshot.id,
        case_id=case.id,
        user_id=user.id,
        facet_type=FacetType.SUMMARY,
        status=FacetStatus.READY,
        content={"summary": "Test summary"}
    )
    
    created = repo.create(db, facet)
    assert created.id == facet.id
    assert created.facet_type == FacetType.SUMMARY


def test_facet_repository_get_by_snapshot_and_type(db, snapshot, case, user):
    """Test getting facet by snapshot and type"""
    repo = FacetRepository()
    
    facet = FacetResult(
        id=str(uuid.uuid4()),
        snapshot_id=snapshot.id,
        case_id=case.id,
        user_id=user.id,
        facet_type=FacetType.SUMMARY,
        status=FacetStatus.READY,
        content={"summary": "Test summary"}
    )
    db.add(facet)
    db.commit()
    
    found = repo.get_by_snapshot_and_type(db, snapshot.id, FacetType.SUMMARY)
    assert found is not None
    assert found.snapshot_id == snapshot.id
    assert found.facet_type == FacetType.SUMMARY


def test_facet_repository_get_by_snapshot_and_type_not_found(db, snapshot):
    """Test getting facet when it doesn't exist"""
    repo = FacetRepository()
    
    found = repo.get_by_snapshot_and_type(db, snapshot.id, FacetType.CLINICAL)
    assert found is None


def test_facet_repository_list_for_case(db, snapshot, case, user):
    """Test listing facets for a case"""
    repo = FacetRepository()
    
    facet1 = FacetResult(
        id=str(uuid.uuid4()),
        snapshot_id=snapshot.id,
        case_id=case.id,
        user_id=user.id,
        facet_type=FacetType.SUMMARY,
        status=FacetStatus.READY,
        content={"summary": "Test summary"}
    )
    facet2 = FacetResult(
        id=str(uuid.uuid4()),
        snapshot_id=snapshot.id,
        case_id=case.id,
        user_id=user.id,
        facet_type=FacetType.CLINICAL,
        status=FacetStatus.READY,
        content={"clinical": "Test clinical"}
    )
    db.add(facet1)
    db.add(facet2)
    db.commit()
    
    facets = repo.list_for_case(db, case.id, user.id)
    assert len(facets) == 2
    assert all(f.case_id == case.id and f.user_id == user.id for f in facets)


def test_facet_repository_list_for_case_filtered(db, snapshot, case, user):
    """Test listing facets is filtered by user"""
    repo = FacetRepository()
    
    # Create another user
    user2_id = str(uuid.uuid4())
    user2 = User(
        id=user2_id,
        email=f"user2-{user2_id[:8]}@example.com",
        name="Test User 2",
        is_active=True
    )
    db.add(user2)
    db.commit()
    
    # Create facets for both users
    facet1 = FacetResult(
        id=str(uuid.uuid4()),
        snapshot_id=snapshot.id,
        case_id=case.id,
        user_id=user.id,
        facet_type=FacetType.SUMMARY,
        status=FacetStatus.READY
    )
    facet2 = FacetResult(
        id=str(uuid.uuid4()),
        snapshot_id=snapshot.id,
        case_id=case.id,
        user_id=user2.id,
        facet_type=FacetType.SUMMARY,
        status=FacetStatus.READY
    )
    db.add(facet1)
    db.add(facet2)
    db.commit()
    
    # List for user 1
    facets_user1 = repo.list_for_case(db, case.id, user.id)
    assert len(facets_user1) == 1
    assert all(f.user_id == user.id for f in facets_user1)


def test_facet_repository_list_for_snapshot(db, snapshot, case, user):
    """Test listing all facets for a snapshot"""
    repo = FacetRepository()
    
    facet1 = FacetResult(
        id=str(uuid.uuid4()),
        snapshot_id=snapshot.id,
        case_id=case.id,
        user_id=user.id,
        facet_type=FacetType.SUMMARY,
        status=FacetStatus.READY
    )
    facet2 = FacetResult(
        id=str(uuid.uuid4()),
        snapshot_id=snapshot.id,
        case_id=case.id,
        user_id=user.id,
        facet_type=FacetType.CLINICAL,
        status=FacetStatus.READY
    )
    
    # Create another snapshot with different facets
    snapshot2 = DashboardSnapshot(
        id=str(uuid.uuid4()),
        case_id=case.id,
        user_id=user.id,
        version=2,
        status=FacetStatus.READY
    )
    facet3 = FacetResult(
        id=str(uuid.uuid4()),
        snapshot_id=snapshot2.id,
        case_id=case.id,
        user_id=user.id,
        facet_type=FacetType.SUMMARY,
        status=FacetStatus.READY
    )
    
    db.add(facet1)
    db.add(facet2)
    db.add(snapshot2)
    db.add(facet3)
    db.commit()
    
    # List facets for snapshot 1
    facets = repo.list_for_snapshot(db, snapshot.id)
    assert len(facets) == 2
    assert all(f.snapshot_id == snapshot.id for f in facets)


def test_facet_repository_get_by_id(db, snapshot, case, user):
    """Test getting facet by ID"""
    repo = FacetRepository()
    
    facet = FacetResult(
        id=str(uuid.uuid4()),
        snapshot_id=snapshot.id,
        case_id=case.id,
        user_id=user.id,
        facet_type=FacetType.SUMMARY,
        status=FacetStatus.READY
    )
    db.add(facet)
    db.commit()
    
    found = repo.get_by_id(db, facet.id)
    assert found is not None
    assert found.id == facet.id


def test_facet_repository_update(db, snapshot, case, user):
    """Test updating a facet"""
    repo = FacetRepository()
    
    facet = FacetResult(
        id=str(uuid.uuid4()),
        snapshot_id=snapshot.id,
        case_id=case.id,
        user_id=user.id,
        facet_type=FacetType.SUMMARY,
        status=FacetStatus.PENDING
    )
    db.add(facet)
    db.commit()
    
    facet.status = FacetStatus.READY
    facet.content = {"summary": "Updated summary"}
    updated = repo.update(db, facet)
    assert updated.status == FacetStatus.READY
    assert updated.content == {"summary": "Updated summary"}
