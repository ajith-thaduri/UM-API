import pytest
from app.repositories.token_blacklist_repository import TokenBlacklistRepository
from app.models.token_blacklist import TokenBlacklist
from app.models.user import User
from app.services.auth_service import create_access_token
from datetime import datetime, timedelta

def test_token_blacklist_add_token(db):
    """Test adding a token to blacklist."""
    repo = TokenBlacklistRepository()
    
    user = User(
        id="blacklist-user-1",
        email="blacklist1@example.com",
        name="Blacklist User",
        is_active=True
    )
    db.add(user)
    db.commit()
    
    token = create_access_token(data={"sub": user.id})
    expires_at = datetime.utcnow() + timedelta(days=7)
    
    blacklisted = repo.add_token(db, token, user.id, expires_at)
    assert blacklisted is not None
    assert blacklisted.user_id == user.id

def test_token_blacklist_is_blacklisted(db):
    """Test checking if token is blacklisted."""
    repo = TokenBlacklistRepository()
    
    user = User(
        id="check-blacklist-user-1",
        email="checkblacklist1@example.com",
        name="Check Blacklist User",
        is_active=True
    )
    db.add(user)
    db.commit()
    
    token = create_access_token(data={"sub": user.id})
    expires_at = datetime.utcnow() + timedelta(days=7)
    
    # Not blacklisted yet
    assert repo.is_blacklisted(db, token) is False
    
    # Add to blacklist
    repo.add_token(db, token, user.id, expires_at)
    
    # Now should be blacklisted
    assert repo.is_blacklisted(db, token) is True

def test_token_blacklist_cleanup_expired(db):
    """Test cleaning up expired tokens."""
    repo = TokenBlacklistRepository()
    
    user1 = User(
        id="cleanup-user-1",
        email="cleanup1@example.com",
        name="Cleanup User 1",
        is_active=True
    )
    user2 = User(
        id="cleanup-user-2",
        email="cleanup2@example.com",
        name="Cleanup User 2",
        is_active=True
    )
    db.add(user1)
    db.add(user2)
    db.commit()
    
    # Create different tokens with different user IDs to ensure different hashes
    token1 = create_access_token(data={"sub": user1.id})
    token2 = create_access_token(data={"sub": user2.id})
    
    # Add expired token
    expired_at = datetime.utcnow() - timedelta(days=1)
    repo.add_token(db, token1, user1.id, expired_at)
    
    # Add non-expired token
    future_at = datetime.utcnow() + timedelta(days=7)
    repo.add_token(db, token2, user2.id, future_at)
    
    # Cleanup
    deleted_count = repo.cleanup_expired(db)
    assert deleted_count >= 1
    
    # Expired should be gone, non-expired should remain
    assert repo.is_blacklisted(db, token1) is False
    assert repo.is_blacklisted(db, token2) is True
