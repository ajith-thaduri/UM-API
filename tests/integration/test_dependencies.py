import pytest
from app.db.dependencies import (
    get_case_repository,
    get_user_repository,
    get_extraction_repository,
    get_decision_repository,
    get_note_repository
)

def test_get_case_repository_dependency(db):
    """Test case repository dependency injection."""
    repo = get_case_repository(db)
    assert repo is not None
    assert hasattr(repo, 'get_by_id')

def test_get_user_repository_dependency(db):
    """Test user repository dependency injection."""
    repo = get_user_repository(db)
    assert repo is not None
    assert hasattr(repo, 'get_by_id')

def test_get_extraction_repository_dependency(db):
    """Test extraction repository dependency injection."""
    repo = get_extraction_repository(db)
    assert repo is not None
    assert hasattr(repo, 'get_by_id')

def test_get_decision_repository_dependency(db):
    """Test decision repository dependency injection."""
    repo = get_decision_repository(db)
    assert repo is not None
    assert hasattr(repo, 'get_by_id')

def test_get_note_repository_dependency(db):
    """Test note repository dependency injection."""
    repo = get_note_repository(db)
    assert repo is not None
    assert hasattr(repo, 'get_by_id')
