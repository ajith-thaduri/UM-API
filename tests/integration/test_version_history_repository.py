import pytest
from app.repositories.version_history_repository import VersionHistoryRepository
from app.models.version_history import VersionHistory, VersionEventType
from app.models.prompt import Prompt
from app.models.user import User

def test_version_history_get_next_version_number(db):
    """Test getting next version number."""
    repo = VersionHistoryRepository()
    
    # Create a prompt to version
    prompt = Prompt(
        id="version-prompt-1",
        category="test",
        name="Version Prompt",
        template="Template",
        variables=[],
        is_active=True
    )
    db.add(prompt)
    db.commit()
    
    # Add first version
    repo.add_entry(
        db=db,
        table_name="prompts",
        ref_id="version-prompt-1",
        event_type=VersionEventType.CREATE,
        snapshot={"template": "Version 1"}
    )
    db.commit()
    
    # Get next version
    next_version = repo.get_next_version_number(db, "prompts", "version-prompt-1")
    assert next_version == 2

def test_version_history_add_entry(db):
    """Test adding version history entry."""
    repo = VersionHistoryRepository()
    
    user = User(
        id="version-user-1",
        email="version1@example.com",
        name="Version User",
        is_active=True
    )
    db.add(user)
    db.commit()
    
    entry = repo.add_entry(
        db=db,
        table_name="test_table",
        ref_id="test-id-1",
        event_type=VersionEventType.CREATE,
        changes={"field": {"old": None, "new": "value"}},
        snapshot={"field": "value"},
        user_id=user.id,
        request_id="req-123"
    )
    db.commit()
    
    assert entry is not None
    assert entry.version_number == 1
    assert entry.event_type == VersionEventType.CREATE

def test_version_history_get_history(db):
    """Test getting version history."""
    repo = VersionHistoryRepository()
    
    # Create multiple versions
    for i in range(3):
        repo.add_entry(
            db=db,
            table_name="test_table",
            ref_id="history-test-1",
            event_type=VersionEventType.UPDATE,
            snapshot={"version": i + 1}
        )
        db.flush()  # Flush so get_next_version_number sees the previous entries
    db.commit()
    
    history = repo.get_history(db, "test_table", "history-test-1")
    assert len(history) == 3
    # Should be ordered by version desc
    assert history[0].version_number == 3

def test_version_history_get_version(db):
    """Test getting specific version."""
    repo = VersionHistoryRepository()
    
    # Create versions
    for i in range(3):
        repo.add_entry(
            db=db,
            table_name="test_table",
            ref_id="version-test-1",
            event_type=VersionEventType.UPDATE,
            snapshot={"version": i + 1}
        )
        db.flush()
    db.commit()
    
    # Get version 2
    version = repo.get_version(db, "test_table", "version-test-1", 2)
    assert version is not None
    assert version.version_number == 2

def test_version_history_get_version_not_found(db):
    """Test getting non-existent version."""
    repo = VersionHistoryRepository()
    version = repo.get_version(db, "test_table", "non-existent", 1)
    assert version is None
