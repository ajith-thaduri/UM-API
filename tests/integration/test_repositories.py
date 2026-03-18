import pytest
from app.repositories.user_repository import UserRepository
from app.repositories.prompt_repository import PromptRepository
from app.repositories.wallet_repository import WalletRepository
from app.models.user import User, UserRole
from app.models.prompt import Prompt
from app.models.wallet import Wallet

def test_user_repository_get_by_email(db):
    """Test getting user by email."""
    repo = UserRepository()
    
    user = User(
        id="repo-user-1",
        email="repo1@example.com",
        name="Repo User",
        is_active=True
    )
    db.add(user)
    db.commit()
    
    found = repo.get_by_email(db, "repo1@example.com")
    assert found is not None
    assert found.email == "repo1@example.com"

def test_user_repository_get_by_email_not_found(db):
    """Test getting non-existent user by email."""
    repo = UserRepository()
    found = repo.get_by_email(db, "nonexistent@example.com")
    assert found is None

def test_user_repository_get_by_role(db):
    """Test getting users by role."""
    repo = UserRepository()
    
    user1 = User(
        id="role-user-1",
        email="role1@example.com",
        name="Role User 1",
        role="um_nurse",
        is_active=True
    )
    user2 = User(
        id="role-user-2",
        email="role2@example.com",
        name="Role User 2",
        role="medical_director",
        is_active=True
    )
    db.add(user1)
    db.add(user2)
    db.commit()
    
    nurses = repo.get_by_role(db, "um_nurse")
    assert len(nurses) >= 1
    assert all(u.role == "um_nurse" for u in nurses)

def test_user_repository_get_active_users(db):
    """Test getting active users."""
    repo = UserRepository()
    
    active_user = User(
        id="active-user-1",
        email="active1@example.com",
        name="Active User",
        is_active=True
    )
    inactive_user = User(
        id="inactive-user-1",
        email="inactive1@example.com",
        name="Inactive User",
        is_active=False
    )
    db.add(active_user)
    db.add(inactive_user)
    db.commit()
    
    active_users = repo.get_active_users(db)
    assert len(active_users) >= 1
    assert all(u.is_active for u in active_users)

def test_user_repository_create(db):
    """Test creating a user."""
    repo = UserRepository()
    
    new_user = User(
        id="create-user-1",
        email="create1@example.com",
        name="Create User",
        is_active=True
    )
    
    created = repo.create(db, new_user)
    assert created.id == "create-user-1"
    assert created.email == "create1@example.com"

def test_user_repository_get_by_id(db):
    """Test getting user by ID."""
    repo = UserRepository()
    
    user = User(
        id="id-user-1",
        email="id1@example.com",
        name="ID User",
        is_active=True
    )
    db.add(user)
    db.commit()
    
    found = repo.get_by_id(db, "id-user-1")
    assert found is not None
    assert found.id == "id-user-1"

def test_prompt_repository_get_by_category(db):
    """Test getting prompts by category."""
    repo = PromptRepository()
    
    prompt1 = Prompt(
        id="cat-prompt-1",
        category="test_category",
        name="Test Prompt",
        template="Template",
        variables=[],
        is_active=True
    )
    prompt2 = Prompt(
        id="cat-prompt-2",
        category="other_category",
        name="Other Prompt",
        template="Template",
        variables=[],
        is_active=True
    )
    db.add(prompt1)
    db.add(prompt2)
    db.commit()
    
    prompts = repo.get_by_category(db, "test_category")
    assert len(prompts) >= 1
    assert all(p.category == "test_category" for p in prompts)

def test_wallet_repository_get_by_user_id(db):
    """Test getting wallet by user ID."""
    repo = WalletRepository()
    
    user = User(
        id="wallet-user-1",
        email="wallet1@example.com",
        name="Wallet User",
        is_active=True
    )
    wallet = Wallet(
        id="wallet-1",
        user_id="wallet-user-1",
        balance=100.00
    )
    db.add(user)
    db.add(wallet)
    db.commit()
    
    found = repo.get_by_user_id(db, "wallet-user-1")
    assert found is not None
    assert found.user_id == "wallet-user-1"

def test_wallet_repository_create_for_user(db):
    """Test creating wallet for user."""
    repo = WalletRepository()
    
    user = User(
        id="wallet-user-2",
        email="wallet2@example.com",
        name="Wallet User 2",
        is_active=True
    )
    db.add(user)
    db.commit()
    
    wallet = repo.create_for_user(db, "wallet-user-2", initial_balance=50.00)
    assert wallet.user_id == "wallet-user-2"
    assert float(wallet.balance) == 50.00
