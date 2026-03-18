import pytest
from app.repositories.transaction_repository import TransactionRepository
from app.models.transaction import Transaction, TransactionType, TransactionStatus
from app.models.wallet import Wallet
from app.models.user import User

def test_transaction_repository_get_by_user_id(db):
    """Test getting transactions by user ID."""
    repo = TransactionRepository()
    
    user = User(
        id="tx-user-1",
        email="txuser1@example.com",
        name="TX User",
        is_active=True
    )
    wallet = Wallet(id="wallet-tx-1", user_id=user.id, balance=100.00)
    db.add(user)
    db.add(wallet)
    db.commit()
    
    # Create transactions
    tx1 = Transaction(
        id="tx-1",
        wallet_id=wallet.id,
        user_id=user.id,
        type=TransactionType.CREDIT,
        amount=50.00,
        status=TransactionStatus.COMPLETED
    )
    tx2 = Transaction(
        id="tx-2",
        wallet_id=wallet.id,
        user_id=user.id,
        type=TransactionType.DEBIT,
        amount=10.00,
        status=TransactionStatus.COMPLETED
    )
    db.add(tx1)
    db.add(tx2)
    db.commit()
    
    transactions = repo.get_by_user_id(db, user.id)
    assert len(transactions) >= 2

def test_transaction_repository_get_by_user_id_with_type_filter(db):
    """Test getting transactions filtered by type."""
    repo = TransactionRepository()
    
    user = User(
        id="tx-filter-user-1",
        email="txfilter1@example.com",
        name="TX Filter User",
        is_active=True
    )
    wallet = Wallet(id="wallet-filter-1", user_id=user.id, balance=100.00)
    db.add(user)
    db.add(wallet)
    db.commit()
    
    tx1 = Transaction(
        id="tx-filter-1",
        wallet_id=wallet.id,
        user_id=user.id,
        type=TransactionType.CREDIT,
        amount=50.00,
        status=TransactionStatus.COMPLETED
    )
    tx2 = Transaction(
        id="tx-filter-2",
        wallet_id=wallet.id,
        user_id=user.id,
        type=TransactionType.DEBIT,
        amount=10.00,
        status=TransactionStatus.COMPLETED
    )
    db.add(tx1)
    db.add(tx2)
    db.commit()
    
    credits = repo.get_by_user_id(db, user.id, transaction_type=TransactionType.CREDIT)
    assert all(t.type == TransactionType.CREDIT for t in credits)

def test_transaction_repository_get_by_wallet_id(db):
    """Test getting transactions by wallet ID."""
    repo = TransactionRepository()
    
    user = User(
        id="wallet-tx-user-1",
        email="wallettx1@example.com",
        name="Wallet TX User",
        is_active=True
    )
    wallet = Wallet(id="wallet-tx-wallet-1", user_id=user.id, balance=100.00)
    db.add(user)
    db.add(wallet)
    db.commit()
    
    tx = Transaction(
        id="wallet-tx-1",
        wallet_id=wallet.id,
        user_id=user.id,
        type=TransactionType.CREDIT,
        amount=25.00,
        status=TransactionStatus.COMPLETED
    )
    db.add(tx)
    db.commit()
    
    transactions = repo.get_by_wallet_id(db, wallet.id)
    assert len(transactions) >= 1
    assert all(t.wallet_id == wallet.id for t in transactions)

def test_transaction_repository_count_by_user(db):
    """Test counting transactions by user."""
    repo = TransactionRepository()
    
    user = User(
        id="count-tx-user-1",
        email="counttx1@example.com",
        name="Count TX User",
        is_active=True
    )
    wallet = Wallet(id="wallet-count-1", user_id=user.id, balance=100.00)
    db.add(user)
    db.add(wallet)
    db.commit()
    
    for i in range(3):
        tx = Transaction(
            id=f"count-tx-{i}",
            wallet_id=wallet.id,
            user_id=user.id,
            type=TransactionType.CREDIT,
            amount=10.00,
            status=TransactionStatus.COMPLETED
        )
        db.add(tx)
    db.commit()
    
    count = repo.count_by_user(db, user.id)
    assert count >= 3

def test_transaction_repository_get_by_stripe_payment_intent(db):
    """Test getting transaction by Stripe payment intent ID."""
    repo = TransactionRepository()
    
    user = User(
        id="stripe-tx-user-1",
        email="stripetx1@example.com",
        name="Stripe TX User",
        is_active=True
    )
    wallet = Wallet(id="wallet-stripe-1", user_id=user.id, balance=100.00)
    db.add(user)
    db.add(wallet)
    db.commit()
    
    tx = Transaction(
        id="stripe-tx-1",
        wallet_id=wallet.id,
        user_id=user.id,
        type=TransactionType.CREDIT,
        amount=50.00,
        stripe_payment_intent_id="pi_test_123",
        status=TransactionStatus.COMPLETED
    )
    db.add(tx)
    db.commit()
    
    found = repo.get_by_stripe_payment_intent(db, "pi_test_123")
    assert found is not None
    assert found.stripe_payment_intent_id == "pi_test_123"
