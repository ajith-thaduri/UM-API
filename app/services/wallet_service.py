"""Wallet service for managing user balance and transactions"""

import uuid
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
from decimal import Decimal
from sqlalchemy.orm import Session

from app.models.wallet import Wallet
from app.models.transaction import Transaction, TransactionType, TransactionStatus
from app.repositories.wallet_repository import WalletRepository
from app.repositories.transaction_repository import TransactionRepository

logger = logging.getLogger(__name__)


class WalletService:
    """Service for managing wallet operations"""

    def __init__(self):
        self.wallet_repo = WalletRepository()
        self.transaction_repo = TransactionRepository()

    def get_wallet(self, db: Session, user_id: str) -> Wallet:
        """
        Get or create wallet for a user

        Args:
            db: Database session
            user_id: User ID

        Returns:
            Wallet instance (created if doesn't exist with $50 trial balance)
        """
        wallet = self.wallet_repo.get_by_user_id(db, user_id)
        if not wallet:
            # Create wallet with $50 trial balance
            wallet = self.wallet_repo.create_for_user(db, user_id, initial_balance=50.00)
            logger.info(f"Created wallet for user {user_id} with $50 trial balance")
        return wallet

    def get_balance(self, db: Session, user_id: str) -> Decimal:
        """
        Get current wallet balance

        Args:
            db: Database session
            user_id: User ID

        Returns:
            Current balance as Decimal
        """
        wallet = self.get_wallet(db, user_id)
        return Decimal(str(wallet.balance))

    def add_funds(
        self,
        db: Session,
        user_id: str,
        amount: Decimal,
        payment_method: str = "stripe",
        description: Optional[str] = None,
        stripe_payment_intent_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Transaction:
        """
        Add funds to wallet

        Args:
            db: Database session
            user_id: User ID
            amount: Amount to add
            payment_method: Payment method (stripe, trial, refund, etc.)
            description: Optional description
            stripe_payment_intent_id: Optional Stripe payment intent ID
            metadata: Optional additional metadata

        Returns:
            Created Transaction instance
        """
        wallet = self.get_wallet(db, user_id)

        # Create credit transaction
        transaction = Transaction(
            id=str(uuid.uuid4()),
            wallet_id=wallet.id,
            user_id=user_id,
            type=TransactionType.CREDIT,
            amount=float(amount),
            description=description or f"Funds added via {payment_method}",
            status=TransactionStatus.COMPLETED,
            payment_method=payment_method,
            stripe_payment_intent_id=stripe_payment_intent_id,
            extra_metadata=metadata
        )

        try:
            db.add(transaction)
            # Update wallet balance
            wallet.balance = Decimal(str(wallet.balance)) + amount
            wallet.updated_at = datetime.utcnow()
            db.commit()
            db.refresh(transaction)
            logger.info(f"Added ${amount} to wallet for user {user_id}")
            return transaction
        except Exception as e:
            logger.error(f"Error adding funds: {e}", exc_info=True)
            db.rollback()
            raise

    def deduct_funds(
        self,
        db: Session,
        user_id: str,
        amount: Decimal,
        description: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Transaction:
        """
        Deduct funds from wallet for usage

        Args:
            db: Database session
            user_id: User ID
            amount: Amount to deduct
            description: Description of the deduction
            metadata: Optional additional metadata

        Returns:
            Created Transaction instance

        Raises:
            ValueError: If insufficient balance
        """
        wallet = self.get_wallet(db, user_id)
        current_balance = Decimal(str(wallet.balance))

        if current_balance < amount:
            raise ValueError(f"Insufficient balance. Current: ${current_balance}, Required: ${amount}")

        # Create debit transaction
        transaction = Transaction(
            id=str(uuid.uuid4()),
            wallet_id=wallet.id,
            user_id=user_id,
            type=TransactionType.DEBIT,
            amount=float(amount),
            description=description,
            status=TransactionStatus.COMPLETED,
            payment_method="usage",
            extra_metadata=metadata
        )

        try:
            db.add(transaction)
            # Update wallet balance
            wallet.balance = current_balance - amount
            wallet.updated_at = datetime.utcnow()
            db.commit()
            db.refresh(transaction)
            logger.info(f"Deducted ${amount} from wallet for user {user_id}: {description}")
            return transaction
        except Exception as e:
            logger.error(f"Error deducting funds: {e}", exc_info=True)
            db.rollback()
            raise

    def get_transaction_history(
        self,
        db: Session,
        user_id: str,
        limit: int = 50,
        offset: int = 0,
        transaction_type: Optional[TransactionType] = None
    ) -> List[Transaction]:
        """
        Get transaction history for a user

        Args:
            db: Database session
            user_id: User ID
            limit: Maximum number of records
            offset: Number of records to skip
            transaction_type: Optional filter by type

        Returns:
            List of Transaction instances
        """
        return self.transaction_repo.get_by_user_id(
            db, user_id, skip=offset, limit=limit, transaction_type=transaction_type
        )

    def check_low_balance(self, db: Session, user_id: str, threshold: Decimal = Decimal("5.00")) -> Dict[str, Any]:
        """
        Check if wallet balance is below threshold

        Args:
            db: Database session
            user_id: User ID
            threshold: Balance threshold (default $5)

        Returns:
            Dictionary with 'is_low' boolean and 'balance' amount
        """
        balance = self.get_balance(db, user_id)
        is_low = balance < threshold

        # Also check token equivalent (10K tokens at average $20/1M tokens = ~$0.20 per 10K)
        # For simplicity, we'll use $5 as the threshold for both USD and token warnings
        return {
            "is_low": is_low,
            "balance": float(balance),
            "threshold": float(threshold),
            "remaining": float(balance - threshold) if balance >= threshold else 0.0
        }

    def get_wallet_summary(self, db: Session, user_id: str) -> Dict[str, Any]:
        """
        Get comprehensive wallet summary

        Args:
            db: Database session
            user_id: User ID

        Returns:
            Dictionary with wallet balance, transaction count, and low balance status
        """
        wallet = self.get_wallet(db, user_id)
        balance = Decimal(str(wallet.balance))
        low_balance_check = self.check_low_balance(db, user_id)

        # Get recent transaction count
        recent_transactions = self.transaction_repo.get_by_user_id(db, user_id, skip=0, limit=10)
        total_transactions = self.transaction_repo.count_by_user(db, user_id)

        return {
            "balance": float(balance),
            "currency": wallet.currency,
            "is_low_balance": low_balance_check["is_low"],
            "threshold": low_balance_check["threshold"],
            "total_transactions": total_transactions,
            "recent_transaction_count": len(recent_transactions),
            "created_at": wallet.created_at.isoformat() if wallet.created_at else None,
            "updated_at": wallet.updated_at.isoformat() if wallet.updated_at else None
        }

    def get_transactions_grouped_by_case(
        self,
        db: Session,
        user_id: str,
        limit: int = 50,
        offset: int = 0,
        transaction_type: Optional[TransactionType] = None
    ) -> List[Dict[str, Any]]:
        """
        Get transactions grouped by case_id
        
        Returns list of grouped transactions with:
        - case_id (or None for non-case transactions)
        - total_amount
        - transaction_count
        - earliest_date
        - latest_date
        - case_name (if available)
        """
        # Get all debit transactions (usage transactions)
        # Use a large limit to get all transactions for grouping
        all_transactions = self.transaction_repo.get_by_user_id(
            db, user_id, skip=0, limit=10000, transaction_type=TransactionType.DEBIT
        )
        
        # Group by case_id
        grouped = {}
        
        for tx in all_transactions:
            case_id = None
            if tx.extra_metadata and isinstance(tx.extra_metadata, dict):
                case_id = tx.extra_metadata.get("case_id")
            
            if case_id:
                if case_id not in grouped:
                    grouped[case_id] = {
                        "case_id": case_id,
                        "total_amount": 0.0,
                        "transaction_count": 0,
                        "earliest_date": tx.created_at,
                        "latest_date": tx.created_at,
                    }
                
                grouped[case_id]["total_amount"] += float(tx.amount)
                grouped[case_id]["transaction_count"] += 1
                
                if tx.created_at < grouped[case_id]["earliest_date"]:
                    grouped[case_id]["earliest_date"] = tx.created_at
                if tx.created_at > grouped[case_id]["latest_date"]:
                    grouped[case_id]["latest_date"] = tx.created_at
        
        # Convert to list and sort by latest_date
        result = list(grouped.values())
        result.sort(key=lambda x: x["latest_date"], reverse=True)
        
        # Add case names if available and convert dates to ISO strings
        from app.repositories.case_repository import CaseRepository
        case_repo = CaseRepository()
        
        for item in result:
            # Convert datetime to ISO string for API response
            item["earliest_date"] = item["earliest_date"].isoformat()
            item["latest_date"] = item["latest_date"].isoformat()
            
            case = case_repo.get_by_id(db, item["case_id"], user_id=user_id)
            if case:
                item["case_name"] = case.case_number
                item["patient_name"] = case.patient_name
            else:
                item["case_name"] = "Unknown Case"
                item["patient_name"] = None
        
        # Apply pagination
        start = offset
        end = offset + limit
        return result[start:end]

    def get_case_transaction_details(
        self,
        db: Session,
        user_id: str,
        case_id: str
    ) -> Dict[str, Any]:
        """
        Get detailed breakdown of all transactions for a specific case
        
        Returns:
        - case_info
        - total_cost
        - breakdown by operation_type
        - breakdown by provider/model
        - individual transactions with token details
        """
        # Get all transactions for this case
        all_transactions = self.transaction_repo.get_by_user_id(
            db, user_id, skip=0, limit=10000, transaction_type=TransactionType.DEBIT
        )
        
        case_transactions = []
        for tx in all_transactions:
            if tx.extra_metadata and isinstance(tx.extra_metadata, dict):
                if tx.extra_metadata.get("case_id") == case_id:
                    case_transactions.append(tx)
        
        # Get case info
        from app.repositories.case_repository import CaseRepository
        case_repo = CaseRepository()
        case = case_repo.get_by_id(db, case_id, user_id=user_id)
        
        # Get usage metrics for detailed token breakdown
        from app.repositories.usage_metrics_repository import UsageMetricsRepository
        usage_repo = UsageMetricsRepository()
        usage_metrics = usage_repo.get_by_case_id(db, case_id)
        
        # Group by operation_type
        by_operation = {}
        by_provider_model = {}
        total_cost = 0.0
        total_prompt_tokens = 0
        total_completion_tokens = 0
        
        for metric in usage_metrics:
            op_type = metric.operation_type
            provider_model = f"{metric.provider}/{metric.model}"
            
            if op_type not in by_operation:
                by_operation[op_type] = {
                    "operation_type": op_type,
                    "total_cost": 0.0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "request_count": 0,
                }
            
            if provider_model not in by_provider_model:
                by_provider_model[provider_model] = {
                    "provider": metric.provider,
                    "model": metric.model,
                    "total_cost": 0.0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "request_count": 0,
                }
            
            cost = float(metric.estimated_cost_usd or 0)
            by_operation[op_type]["total_cost"] += cost
            by_operation[op_type]["prompt_tokens"] += metric.prompt_tokens
            by_operation[op_type]["completion_tokens"] += metric.completion_tokens
            by_operation[op_type]["request_count"] += 1
            
            by_provider_model[provider_model]["total_cost"] += cost
            by_provider_model[provider_model]["prompt_tokens"] += metric.prompt_tokens
            by_provider_model[provider_model]["completion_tokens"] += metric.completion_tokens
            by_provider_model[provider_model]["request_count"] += 1
            
            total_cost += cost
            total_prompt_tokens += metric.prompt_tokens
            total_completion_tokens += metric.completion_tokens
        
        return {
            "case_id": case_id,
            "case_info": {
                "case_number": case.case_number if case else None,
                "patient_name": case.patient_name if case else None,
                "status": case.status.value if case else None,
            },
            "summary": {
                "total_cost": total_cost,
                "total_prompt_tokens": total_prompt_tokens,
                "total_completion_tokens": total_completion_tokens,
                "total_transactions": len(case_transactions),
                "total_llm_requests": len(usage_metrics),
            },
            "breakdown_by_operation": list(by_operation.values()),
            "breakdown_by_provider_model": list(by_provider_model.values()),
            "transactions": [
                {
                    "id": tx.id,
                    "amount": float(tx.amount),
                    "description": tx.description,
                    "created_at": tx.created_at.isoformat(),
                    "metadata": tx.extra_metadata,
                }
                for tx in case_transactions
            ],
            "usage_metrics": [
                {
                    "id": m.id,
                    "operation_type": m.operation_type,
                    "provider": m.provider,
                    "model": m.model,
                    "prompt_tokens": m.prompt_tokens,
                    "completion_tokens": m.completion_tokens,
                    "total_tokens": m.total_tokens,
                    "cost": float(m.estimated_cost_usd or 0),
                    "timestamp": m.request_timestamp.isoformat(),
                }
                for m in usage_metrics
            ],
        }

