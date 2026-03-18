"""Integration tests for SourceLinkRepository"""

import pytest
import uuid
from app.repositories.source_link_repository import SourceLinkRepository
from app.models.dashboard import SourceLink, FacetResult, FacetType, FacetStatus, DashboardSnapshot
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


@pytest.fixture
def facet(db, snapshot, case, user):
    """Create a test facet result"""
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
    return facet


def test_source_link_repository_create(db, facet, case, user):
    """Test creating a source link"""
    repo = SourceLinkRepository()
    
    source_link = SourceLink(
        id=str(uuid.uuid4()),
        case_id=case.id,
        user_id=user.id,
        facet_id=facet.id,
        item_id="item-1",
        file_id="file-1",
        file_name="test.pdf",
        page_number=1,
        snippet="Test snippet",
        full_text="Test full text"
    )
    
    created = repo.create(db, source_link)
    assert created.id == source_link.id
    assert created.item_id == "item-1"


def test_source_link_repository_list_for_facet(db, facet, case, user):
    """Test listing source links for a facet"""
    repo = SourceLinkRepository()
    
    source_link1 = SourceLink(
        id=str(uuid.uuid4()),
        case_id=case.id,
        user_id=user.id,
        facet_id=facet.id,
        item_id="item-1",
        file_id="file-1",
        file_name="test1.pdf",
        page_number=1
    )
    source_link2 = SourceLink(
        id=str(uuid.uuid4()),
        case_id=case.id,
        user_id=user.id,
        facet_id=facet.id,
        item_id="item-2",
        file_id="file-2",
        file_name="test2.pdf",
        page_number=2
    )
    
    # Create another facet with different links
    facet2 = FacetResult(
        id=str(uuid.uuid4()),
        snapshot_id=facet.snapshot_id,
        case_id=case.id,
        user_id=user.id,
        facet_type=FacetType.CLINICAL,
        status=FacetStatus.READY
    )
    source_link3 = SourceLink(
        id=str(uuid.uuid4()),
        case_id=case.id,
        user_id=user.id,
        facet_id=facet2.id,
        item_id="item-3",
        file_id="file-3",
        file_name="test3.pdf",
        page_number=3
    )
    
    db.add(source_link1)
    db.add(source_link2)
    db.add(facet2)
    db.add(source_link3)
    db.commit()
    
    # List links for facet 1
    links = repo.list_for_facet(db, facet.id)
    assert len(links) == 2
    assert all(link.facet_id == facet.id for link in links)


def test_source_link_repository_list_for_case(db, facet, case, user):
    """Test listing source links for a case"""
    repo = SourceLinkRepository()
    
    source_link1 = SourceLink(
        id=str(uuid.uuid4()),
        case_id=case.id,
        user_id=user.id,
        facet_id=facet.id,
        item_id="item-1",
        file_id="file-1",
        file_name="test1.pdf",
        page_number=1
    )
    source_link2 = SourceLink(
        id=str(uuid.uuid4()),
        case_id=case.id,
        user_id=user.id,
        facet_id=facet.id,
        item_id="item-2",
        file_id="file-2",
        file_name="test2.pdf",
        page_number=2
    )
    db.add(source_link1)
    db.add(source_link2)
    db.commit()
    
    # List links for case
    links = repo.list_for_case(db, case.id, user.id)
    assert len(links) == 2
    assert all(link.case_id == case.id and link.user_id == user.id for link in links)


def test_source_link_repository_list_for_case_filtered(db, facet, case, user):
    """Test listing source links is filtered by user"""
    repo = SourceLinkRepository()
    
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
    
    # Create links for both users
    source_link1 = SourceLink(
        id=str(uuid.uuid4()),
        case_id=case.id,
        user_id=user.id,
        facet_id=facet.id,
        item_id="item-1",
        file_id="file-1",
        file_name="test1.pdf",
        page_number=1
    )
    source_link2 = SourceLink(
        id=str(uuid.uuid4()),
        case_id=case.id,
        user_id=user2.id,
        facet_id=facet.id,
        item_id="item-2",
        file_id="file-2",
        file_name="test2.pdf",
        page_number=2
    )
    db.add(source_link1)
    db.add(source_link2)
    db.commit()
    
    # List links for user 1
    links_user1 = repo.list_for_case(db, case.id, user.id)
    assert len(links_user1) == 1
    assert all(link.user_id == user.id for link in links_user1)


def test_source_link_repository_get_by_id(db, facet, case, user):
    """Test getting source link by ID"""
    repo = SourceLinkRepository()
    
    source_link = SourceLink(
        id=str(uuid.uuid4()),
        case_id=case.id,
        user_id=user.id,
        facet_id=facet.id,
        item_id="item-1",
        file_id="file-1",
        file_name="test.pdf",
        page_number=1
    )
    db.add(source_link)
    db.commit()
    
    found = repo.get_by_id(db, source_link.id)
    assert found is not None
    assert found.id == source_link.id


def test_source_link_repository_update(db, facet, case, user):
    """Test updating a source link"""
    repo = SourceLinkRepository()
    
    source_link = SourceLink(
        id=str(uuid.uuid4()),
        case_id=case.id,
        user_id=user.id,
        facet_id=facet.id,
        item_id="item-1",
        file_id="file-1",
        file_name="test.pdf",
        page_number=1,
        snippet="Original snippet"
    )
    db.add(source_link)
    db.commit()
    
    source_link.snippet = "Updated snippet"
    updated = repo.update(db, source_link)
    assert updated.snippet == "Updated snippet"


def test_source_link_repository_delete(db, facet, case, user):
    """Test deleting a source link"""
    repo = SourceLinkRepository()
    
    source_link = SourceLink(
        id=str(uuid.uuid4()),
        case_id=case.id,
        user_id=user.id,
        facet_id=facet.id,
        item_id="item-1",
        file_id="file-1",
        file_name="test.pdf",
        page_number=1
    )
    db.add(source_link)
    db.commit()
    
    repo.delete(db, source_link.id)
    
    # Verify deleted
    found = repo.get_by_id(db, source_link.id)
    assert found is None
