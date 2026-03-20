"""Wallet repository"""

from typing import Optional
from sqlalchemy.orm import Session

from app.repositories.base import BaseRepository
from app.models.wallet import Wallet


class WalletRepository(BaseRepository[Wallet]):
    """Repository for Wallet model"""

    def __init__(self):
        super().__init__(Wallet)

    def get_by_user_id(self, db: Session, user_id: str) -> Optional[Wallet]:
        """
        Get wallet by user ID

        Args:
            db: Database session
            user_id: User ID

        Returns:
            Wallet instance or None
        """
        return db.query(Wallet).filter(Wallet.user_id == user_id).first()

    def create_for_user(self, db: Session, user_id: str, initial_balance: float = 50.00) -> Wallet:
        """
        Create a new wallet for a user with initial balance

        Args:
            db: Database session
            user_id: User ID
            initial_balance: Initial balance (default $50 trial)

        Returns:
            Created Wallet instance
        """
        import uuid
        wallet = Wallet(
            id=str(uuid.uuid4()),
            user_id=user_id,
            balance=initial_balance,
            currency="USD"
        )
        return self.create(db, wallet)

