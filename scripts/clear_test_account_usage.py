#!/usr/bin/env python3
"""
Script to clear all token consumption data and reset wallet for a test account
Usage: python clear_test_account_usage.py <test_account_email>
"""

import sys
import os
from pathlib import Path
from decimal import Decimal

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from app.db.session import SessionLocal
from app.repositories.user_repository import UserRepository
from app.repositories.usage_metrics_repository import UsageMetricsRepository
from app.repositories.wallet_repository import WalletRepository
from app.models.transaction import Transaction
from sqlalchemy import delete
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def clear_test_account_usage(test_email: str):
    """
    Clear all usage metrics and reset wallet for a test account
    
    Args:
        test_email: Email of the test account
    """
    db = SessionLocal()
    try:
        # Find the test account
        user_repo = UserRepository()
        user = user_repo.get_by_email(db, test_email)
        
        if not user:
            logger.error(f"User with email '{test_email}' not found")
            return False
        
        logger.info(f"Found user: {user.email} (ID: {user.id})")
        
        # 1. Clear usage metrics
        usage_repo = UsageMetricsRepository()
        all_metrics = usage_repo.get_by_user_id(db, user.id, skip=0, limit=100000)
        metrics_count = len(all_metrics)
        deleted_metrics = 0
        
        if metrics_count > 0:
            logger.info(f"Found {metrics_count} usage metric records to delete")
            deleted_metrics = db.query(usage_repo.model).filter(
                usage_repo.model.user_id == user.id
            ).delete(synchronize_session=False)
            logger.info(f"Successfully deleted {deleted_metrics} usage metric records")
        else:
            logger.info("No usage metrics found")
        
        # 2. Reset wallet balance and clear transactions
        wallet_repo = WalletRepository()
        wallet = wallet_repo.get_by_user_id(db, user.id)
        deleted_transactions = 0
        
        if wallet:
            logger.info(f"Found wallet: Balance ${wallet.balance}")
            
            # Delete all transactions
            deleted_transactions = db.query(Transaction).filter(
                Transaction.wallet_id == wallet.id
            ).delete(synchronize_session=False)
            logger.info(f"Deleted {deleted_transactions} transaction records")
            
            # Reset wallet balance to default $50.00
            wallet.balance = Decimal('50.00')
            wallet.updated_at = datetime.utcnow()
            logger.info(f"Reset wallet balance to $50.00")
        else:
            logger.info("No wallet found for user (will be created on next usage)")
        
        db.commit()
        
        logger.info("=" * 60)
        logger.info(f"✅ Successfully reset test account: {test_email}")
        logger.info(f"   - Deleted {deleted_metrics} usage metric records")
        logger.info(f"   - Deleted {deleted_transactions} transaction records")
        if wallet:
            logger.info(f"   - Reset wallet balance to $50.00")
        logger.info("=" * 60)
        
        return True
        
    except Exception as e:
        logger.error(f"Error clearing usage data: {e}", exc_info=True)
        db.rollback()
        return False
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python clear_test_account_usage.py <test_account_email>")
        print("Example: python clear_test_account_usage.py test@example.com")
        sys.exit(1)
    
    test_email = sys.argv[1]
    success = clear_test_account_usage(test_email)
    sys.exit(0 if success else 1)

