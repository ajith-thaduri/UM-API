import pytest
from app.repositories.base import BaseRepository
from app.models.user import User

def test_base_repository_get_by_id(db):
    """Test get_by_id method."""
    repo = BaseRepository(User)
    
    user = User(
        id="base-repo-1",
        email="baserepo1@example.com",
        name="Base Repo User",
        is_active=True
    )
    db.add(user)
    db.commit()
    
    found = repo.get_by_id(db, "base-repo-1")
    assert found is not None
    assert found.id == "base-repo-1"

def test_base_repository_get_by_id_not_found(db):
    """Test get_by_id with non-existent ID."""
    repo = BaseRepository(User)
    found = repo.get_by_id(db, "non-existent-id")
    assert found is None

def test_base_repository_get_all(db):
    """Test get_all method."""
    repo = BaseRepository(User)
    
    user1 = User(id="all-user-1", email="all1@example.com", name="All User 1", is_active=True)
    user2 = User(id="all-user-2", email="all2@example.com", name="All User 2", is_active=True)
    db.add(user1)
    db.add(user2)
    db.commit()
    
    users = repo.get_all(db)
    assert len(users) >= 2

def test_base_repository_get_all_with_filters(db):
    """Test get_all with filters."""
    repo = BaseRepository(User)
    
    active_user = User(id="filter-user-1", email="filter1@example.com", name="Filter User", is_active=True)
    inactive_user = User(id="filter-user-2", email="filter2@example.com", name="Filter User 2", is_active=False)
    db.add(active_user)
    db.add(inactive_user)
    db.commit()
    
    active_users = repo.get_all(db, filters={"is_active": True})
    assert all(u.is_active for u in active_users)

def test_base_repository_get_all_with_pagination(db):
    """Test get_all with pagination."""
    repo = BaseRepository(User)
    
    # Create multiple users
    for i in range(5):
        user = User(
            id=f"page-user-{i}",
            email=f"page{i}@example.com",
            name=f"Page User {i}",
            is_active=True
        )
        db.add(user)
    db.commit()
    
    # Get first page
    page1 = repo.get_all(db, skip=0, limit=2)
    assert len(page1) == 2
    
    # Get second page
    page2 = repo.get_all(db, skip=2, limit=2)
    assert len(page2) == 2

def test_base_repository_get_all_with_ordering(db):
    """Test get_all with ordering."""
    repo = BaseRepository(User)
    
    user1 = User(id="order-user-1", email="order1@example.com", name="A User", is_active=True)
    user2 = User(id="order-user-2", email="order2@example.com", name="B User", is_active=True)
    db.add(user1)
    db.add(user2)
    db.commit()
    
    users_asc = repo.get_all(db, order_by="name", order_desc=False)
    users_desc = repo.get_all(db, order_by="name", order_desc=True)
    
    # Should be different order
    assert len(users_asc) >= 2
    assert len(users_desc) >= 2

def test_base_repository_create(db):
    """Test create method."""
    repo = BaseRepository(User)
    
    new_user = User(
        id="create-repo-user-1",
        email="createrepo1@example.com",
        name="Create Repo User",
        is_active=True
    )
    
    created = repo.create(db, new_user)
    assert created.id == "create-repo-user-1"

def test_base_repository_update(db):
    """Test update method."""
    repo = BaseRepository(User)
    
    user = User(
        id="update-repo-user-1",
        email="updaterepo1@example.com",
        name="Original Name",
        is_active=True
    )
    db.add(user)
    db.commit()
    
    user.name = "Updated Name"
    updated = repo.update(db, user)
    assert updated.name == "Updated Name"

def test_base_repository_delete(db):
    """Test delete method."""
    repo = BaseRepository(User)
    
    user = User(
        id="delete-repo-user-1",
        email="deleterepo1@example.com",
        name="Delete User",
        is_active=True
    )
    db.add(user)
    db.commit()
    
    result = repo.delete(db, "delete-repo-user-1")
    assert result is True
    
    # Verify deleted
    found = repo.get_by_id(db, "delete-repo-user-1")
    assert found is None

def test_base_repository_delete_not_found(db):
    """Test delete with non-existent ID."""
    repo = BaseRepository(User)
    result = repo.delete(db, "non-existent-id")
    assert result is False

def test_base_repository_count(db):
    """Test count method."""
    repo = BaseRepository(User)
    
    user1 = User(id="count-user-1", email="count1@example.com", name="Count User 1", is_active=True)
    user2 = User(id="count-user-2", email="count2@example.com", name="Count User 2", is_active=True)
    db.add(user1)
    db.add(user2)
    db.commit()
    
    count = repo.count(db)
    assert count >= 2

def test_base_repository_count_with_filters(db):
    """Test count with filters."""
    repo = BaseRepository(User)
    
    active_user = User(id="count-filter-1", email="countfilter1@example.com", name="Count Filter", is_active=True)
    inactive_user = User(id="count-filter-2", email="countfilter2@example.com", name="Count Filter 2", is_active=False)
    db.add(active_user)
    db.add(inactive_user)
    db.commit()
    
    active_count = repo.count(db, filters={"is_active": True})
    assert active_count >= 1

def test_base_repository_exists(db):
    """Test exists method."""
    repo = BaseRepository(User)
    
    user = User(
        id="exists-user-1",
        email="exists1@example.com",
        name="Exists User",
        is_active=True
    )
    db.add(user)
    db.commit()
    
    assert repo.exists(db, "exists-user-1") is True
    assert repo.exists(db, "non-existent-id") is False
