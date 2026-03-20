"""Token blacklist repository"""

from typing import Optional
from sqlalchemy.orm import Session
from datetime import datetime
import hashlib

from app.repositories.base import BaseRepository
from app.models.token_blacklist import TokenBlacklist


class TokenBlacklistRepository(BaseRepository[TokenBlacklist]):
    """Repository for TokenBlacklist model"""

    def __init__(self):
        super().__init__(TokenBlacklist)

    def _hash_token(self, token: str) -> str:
        """Hash a token for storage (SHA-256)"""
        return hashlib.sha256(token.encode()).hexdigest()

    def add_token(self, db: Session, token: str, user_id: str, expires_at: datetime) -> TokenBlacklist:
        """
        Add a token to the blacklist.
        Idempotent: if the token is already blacklisted, returns the existing record without error.

        Args:
            db: Database session
            token: JWT token string
            user_id: User ID
            expires_at: When the token expires

        Returns:
            TokenBlacklist instance
        """
        token_hash = self._hash_token(token)
        existing = db.query(TokenBlacklist).filter(TokenBlacklist.token_hash == token_hash).first()
        if existing:
            return existing
        blacklisted_token = TokenBlacklist(
            id=token_hash,  # Use hash as ID for uniqueness
            token_hash=token_hash,
            user_id=user_id,
            expires_at=expires_at,
            blacklisted_at=datetime.utcnow(),
        )
        db.add(blacklisted_token)
        db.commit()
        db.refresh(blacklisted_token)
        return blacklisted_token

    def is_blacklisted(self, db: Session, token: str) -> bool:
        """
        Check if a token is blacklisted

        Args:
            db: Database session
            token: JWT token string

        Returns:
            True if token is blacklisted, False otherwise
        """
        token_hash = self._hash_token(token)
        blacklisted = db.query(TokenBlacklist).filter(
            TokenBlacklist.token_hash == token_hash
        ).first()
        return blacklisted is not None

    def cleanup_expired(self, db: Session) -> int:
        """
        Remove expired blacklist entries (tokens that have passed their expiration)

        Args:
            db: Database session

        Returns:
            Number of entries removed
        """
        now = datetime.utcnow()
        deleted = db.query(TokenBlacklist).filter(
            TokenBlacklist.expires_at < now
        ).delete()
        db.commit()
        return deleted

