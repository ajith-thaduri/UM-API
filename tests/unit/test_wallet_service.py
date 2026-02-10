import pytest
from unittest.mock import MagicMock
from decimal import Decimal
from app.services.wallet_service import WalletService
from app.models.wallet import Wallet
from app.models.user import User
from app.models.transaction import Transaction, TransactionType, TransactionStatus

def test_wallet_service_add_funds_logic():
    """Test that add_funds correctly calculates the new balance."""
    # Mock dependencies
    mock_db = MagicMock()
    mock_wallet_repo = MagicMock()
    
    # Setup service
    service = WalletService()
    service.wallet_repo = mock_wallet_repo
    
    # Setup mock data
    user_id = "test-user-123"
    initial_balance = Decimal("50.00")
    amount_to_add = Decimal("25.50")
    
    mock_wallet = Wallet(id="wallet-1", user_id=user_id, balance=initial_balance)
    mock_wallet_repo.get_by_user_id.return_value = mock_wallet
    
    # Execute
    transaction = service.add_funds(mock_db, user_id, amount_to_add)
    
    # Assert
    assert mock_wallet.balance == Decimal("75.50")
    assert mock_db.add.called
    assert mock_db.commit.called

def test_wallet_service_get_balance(db):
    """Test getting wallet balance."""
    service = WalletService()
    
    user = User(
        id="balance-user-1",
        email="balance1@example.com",
        name="Balance User",
        is_active=True
    )
    db.add(user)
    db.commit()
    
    # First call should create wallet
    balance = service.get_balance(db, "balance-user-1")
    assert balance >= Decimal("50.00")  # Default trial balance

def test_wallet_service_deduct_funds_success(db):
    """Test successful fund deduction."""
    service = WalletService()
    
    user = User(
        id="deduct-user-1",
        email="deduct1@example.com",
        name="Deduct User",
        is_active=True
    )
    db.add(user)
    db.commit()
    
    # Get wallet (creates with $50)
    wallet = service.get_wallet(db, "deduct-user-1")
    
    # Deduct funds
    transaction = service.deduct_funds(
        db, "deduct-user-1", Decimal("10.00"), "Test deduction"
    )
    
    assert transaction.type == TransactionType.DEBIT
    assert float(transaction.amount) == 10.00
    
    # Check balance decreased
    updated_wallet = service.get_wallet(db, "deduct-user-1")
    assert float(updated_wallet.balance) == 40.00

def test_wallet_service_deduct_funds_insufficient_balance(db):
    """Test fund deduction with insufficient balance."""
    service = WalletService()
    
    user = User(
        id="insufficient-user-1",
        email="insufficient1@example.com",
        name="Insufficient User",
        is_active=True
    )
    db.add(user)
    db.commit()
    
    # Get wallet (creates with $50)
    service.get_wallet(db, "insufficient-user-1")
    
    # Try to deduct more than balance
    with pytest.raises(ValueError, match="Insufficient balance"):
        service.deduct_funds(
            db, "insufficient-user-1", Decimal("100.00"), "Too much"
        )

def test_wallet_service_check_low_balance(db):
    """Test low balance check."""
    service = WalletService()
    
    user = User(
        id="lowbalance-user-1",
        email="lowbalance1@example.com",
        name="Low Balance User",
        is_active=True
    )
    db.add(user)
    db.commit()
    
    # Check with default threshold ($5)
    result = service.check_low_balance(db, "lowbalance-user-1")
    assert "is_low" in result
    assert "balance" in result
    assert result["balance"] >= 50.00  # Should have trial balance
    assert result["is_low"] is False  # $50 > $5 threshold

def test_wallet_service_get_transaction_history(db):
    """Test getting transaction history."""
    service = WalletService()
    
    user = User(
        id="history-user-1",
        email="history1@example.com",
        name="History User",
        is_active=True
    )
    db.add(user)
    db.commit()
    
    # Add some funds to create transactions
    service.add_funds(db, "history-user-1", Decimal("20.00"), "Test add")
    service.deduct_funds(db, "history-user-1", Decimal("5.00"), "Test deduct")
    
    # Get history
    transactions = service.get_transaction_history(db, "history-user-1")
    assert len(transactions) >= 2

def test_wallet_service_get_wallet_summary(db):
    """Test getting wallet summary."""
    service = WalletService()
    
    user = User(
        id="summary-user-1",
        email="summary1@example.com",
        name="Summary User",
        is_active=True
    )
    db.add(user)
    db.commit()
    
    # Add some transactions
    service.add_funds(db, "summary-user-1", Decimal("15.00"), "Test")
    
    summary = service.get_wallet_summary(db, "summary-user-1")
    assert "balance" in summary
    assert "total_transactions" in summary
    assert summary["total_transactions"] >= 1
