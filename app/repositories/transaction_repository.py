"""Transaction repository"""

from typing import Optional, List
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.repositories.base import BaseRepository
from app.models.transaction import Transaction, TransactionType, TransactionStatus


class TransactionRepository(BaseRepository[Transaction]):
    """Repository for Transaction model"""

    def __init__(self):
        super().__init__(Transaction)

    def get_by_user_id(
        self,
        db: Session,
        user_id: str,
        skip: int = 0,
        limit: int = 100,
        transaction_type: Optional[TransactionType] = None,
        status: Optional[TransactionStatus] = None
    ) -> List[Transaction]:
        """
        Get transactions for a user with optional filters

        Args:
            db: Database session
            user_id: User ID
            skip: Number of records to skip
            limit: Maximum number of records
            transaction_type: Optional filter by type (credit/debit)
            status: Optional filter by status

        Returns:
            List of Transaction instances
        """
        query = db.query(Transaction).filter(Transaction.user_id == user_id)

        if transaction_type:
            query = query.filter(Transaction.type == transaction_type)
        if status:
            query = query.filter(Transaction.status == status)

        return query.order_by(desc(Transaction.created_at)).offset(skip).limit(limit).all()

    def get_by_wallet_id(
        self,
        db: Session,
        wallet_id: str,
        skip: int = 0,
        limit: int = 100
    ) -> List[Transaction]:
        """
        Get transactions for a wallet

        Args:
            db: Database session
            wallet_id: Wallet ID
            skip: Number of records to skip
            limit: Maximum number of records

        Returns:
            List of Transaction instances
        """
        return (
            db.query(Transaction)
            .filter(Transaction.wallet_id == wallet_id)
            .order_by(desc(Transaction.created_at))
            .offset(skip)
            .limit(limit)
            .all()
        )

    def get_by_stripe_payment_intent(
        self,
        db: Session,
        payment_intent_id: str
    ) -> Optional[Transaction]:
        """
        Get transaction by Stripe payment intent ID

        Args:
            db: Database session
            payment_intent_id: Stripe payment intent ID

        Returns:
            Transaction instance or None
        """
        return (
            db.query(Transaction)
            .filter(Transaction.stripe_payment_intent_id == payment_intent_id)
            .first()
        )

    def count_by_user(
        self,
        db: Session,
        user_id: str,
        transaction_type: Optional[TransactionType] = None,
        status: Optional[TransactionStatus] = None
    ) -> int:
        """
        Count transactions for a user with optional filters

        Args:
            db: Database session
            user_id: User ID
            transaction_type: Optional filter by type
            status: Optional filter by status

        Returns:
            Count of transactions
        """
        query = db.query(Transaction).filter(Transaction.user_id == user_id)

        if transaction_type:
            query = query.filter(Transaction.type == transaction_type)
        if status:
            query = query.filter(Transaction.status == status)

        return query.count()

