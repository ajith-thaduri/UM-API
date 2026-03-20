"""Integration tests for DashboardSnapshotRepository"""

import pytest
import uuid
from app.repositories.dashboard_snapshot_repository import DashboardSnapshotRepository
from app.models.dashboard import DashboardSnapshot, FacetStatus
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


def test_dashboard_snapshot_repository_create(db, case, user):
    """Test creating a dashboard snapshot"""
    repo = DashboardSnapshotRepository()
    
    snapshot = DashboardSnapshot(
        id=str(uuid.uuid4()),
        case_id=case.id,
        user_id=user.id,
        version=1,
        status=FacetStatus.READY
    )
    
    created = repo.create(db, snapshot)
    assert created.id == snapshot.id
    assert created.version == 1


def test_dashboard_snapshot_repository_get_latest_for_case(db, case, user):
    """Test getting latest snapshot for a case"""
    repo = DashboardSnapshotRepository()
    
    # Create multiple snapshots with different versions
    snapshot1 = DashboardSnapshot(
        id=str(uuid.uuid4()),
        case_id=case.id,
        user_id=user.id,
        version=1,
        status=FacetStatus.READY
    )
    snapshot2 = DashboardSnapshot(
        id=str(uuid.uuid4()),
        case_id=case.id,
        user_id=user.id,
        version=2,
        status=FacetStatus.READY
    )
    snapshot3 = DashboardSnapshot(
        id=str(uuid.uuid4()),
        case_id=case.id,
        user_id=user.id,
        version=3,
        status=FacetStatus.READY
    )
    
    db.add(snapshot1)
    db.add(snapshot2)
    db.add(snapshot3)
    db.commit()
    
    latest = repo.get_latest_for_case(db, case.id, user.id)
    assert latest is not None
    assert latest.version == 3


def test_dashboard_snapshot_repository_get_latest_for_case_filtered(db, case, user):
    """Test getting latest snapshot is filtered by user"""
    repo = DashboardSnapshotRepository()
    
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
    
    # Create snapshots for both users
    snapshot1 = DashboardSnapshot(
        id=str(uuid.uuid4()),
        case_id=case.id,
        user_id=user.id,
        version=1,
        status=FacetStatus.READY
    )
    snapshot2 = DashboardSnapshot(
        id=str(uuid.uuid4()),
        case_id=case.id,
        user_id=user2.id,
        version=2,
        status=FacetStatus.READY
    )
    
    db.add(snapshot1)
    db.add(snapshot2)
    db.commit()
    
    # Get latest for user 1
    latest_user1 = repo.get_latest_for_case(db, case.id, user.id)
    assert latest_user1 is not None
    assert latest_user1.user_id == user.id
    assert latest_user1.version == 1
    
    # Get latest for user 2
    latest_user2 = repo.get_latest_for_case(db, case.id, user2.id)
    assert latest_user2 is not None
    assert latest_user2.user_id == user2.id
    assert latest_user2.version == 2


def test_dashboard_snapshot_repository_get_latest_for_case_not_found(db, case, user):
    """Test getting latest snapshot when none exists"""
    repo = DashboardSnapshotRepository()
    
    latest = repo.get_latest_for_case(db, case.id, user.id)
    assert latest is None


def test_dashboard_snapshot_repository_next_version(db, case, user):
    """Test getting next version number"""
    repo = DashboardSnapshotRepository()
    
    # No snapshots exist, should return 1
    next_version = repo.next_version(db, case.id, user.id)
    assert next_version == 1
    
    # Create snapshot with version 1
    snapshot1 = DashboardSnapshot(
        id=str(uuid.uuid4()),
        case_id=case.id,
        user_id=user.id,
        version=1,
        status=FacetStatus.READY
    )
    db.add(snapshot1)
    db.commit()
    
    # Next version should be 2
    next_version = repo.next_version(db, case.id, user.id)
    assert next_version == 2
    
    # Create snapshot with version 2
    snapshot2 = DashboardSnapshot(
        id=str(uuid.uuid4()),
        case_id=case.id,
        user_id=user.id,
        version=2,
        status=FacetStatus.READY
    )
    db.add(snapshot2)
    db.commit()
    
    # Next version should be 3
    next_version = repo.next_version(db, case.id, user.id)
    assert next_version == 3


def test_dashboard_snapshot_repository_get_by_id(db, case, user):
    """Test getting snapshot by ID"""
    repo = DashboardSnapshotRepository()
    
    snapshot = DashboardSnapshot(
        id=str(uuid.uuid4()),
        case_id=case.id,
        user_id=user.id,
        version=1,
        status=FacetStatus.READY
    )
    db.add(snapshot)
    db.commit()
    
    found = repo.get_by_id(db, snapshot.id)
    assert found is not None
    assert found.id == snapshot.id


def test_dashboard_snapshot_repository_update(db, case, user):
    """Test updating a snapshot"""
    repo = DashboardSnapshotRepository()
    
    snapshot = DashboardSnapshot(
        id=str(uuid.uuid4()),
        case_id=case.id,
        user_id=user.id,
        version=1,
        status=FacetStatus.PENDING
    )
    db.add(snapshot)
    db.commit()
    
    snapshot.status = FacetStatus.READY
    updated = repo.update(db, snapshot)
    assert updated.status == FacetStatus.READY
