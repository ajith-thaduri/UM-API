import pytest
from fastapi import status
from app.models.user import User
from app.models.wallet import Wallet
from app.models.transaction import Transaction, TransactionType
from app.services.auth_service import create_access_token

def get_auth_headers(client, email="wallet@example.com", password="password123"):
    """Helper to register and get auth token."""
    reg_data = {"email": email, "password": password, "name": "Test User"}
    response = client.post("/api/v1/auth/register", json=reg_data)
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}

def test_get_wallet_balance(client, db):
    """Test getting wallet balance."""
    headers = get_auth_headers(client, "balance@example.com")
    
    response = client.get("/api/v1/wallet/balance", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    assert "balance" in response.json()
    assert response.json()["balance"] >= 0

def test_get_wallet_summary(client, db):
    """Test getting wallet summary."""
    headers = get_auth_headers(client, "summary@example.com")
    
    response = client.get("/api/v1/wallet/summary", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    assert "balance" in response.json()
    assert "total_transactions" in response.json()

def test_add_funds(client, db):
    """Test adding funds to wallet."""
    headers = get_auth_headers(client, "addfunds@example.com")
    
    add_data = {
        "amount": 25.50,
        "payment_method": "test"
    }
    response = client.post("/api/v1/wallet/add-funds", json=add_data, headers=headers)
    assert response.status_code == status.HTTP_200_OK
    assert "amount" in response.json()

def test_get_transactions(client, db):
    """Test getting transaction history."""
    headers = get_auth_headers(client, "transactions@example.com")
    
    # Add some funds first to create transactions
    client.post("/api/v1/wallet/add-funds", json={"amount": 10.0, "payment_method": "test"}, headers=headers)
    
    response = client.get("/api/v1/wallet/transactions", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    assert "transactions" in response.json()
    assert "total" in response.json()

def test_get_transactions_with_type_filter(client, db):
    """Test getting transactions filtered by type."""
    headers = get_auth_headers(client, "filter@example.com")
    
    # Add funds to create a credit transaction
    client.post("/api/v1/wallet/add-funds", json={"amount": 15.0, "payment_method": "test"}, headers=headers)
    
    response = client.get("/api/v1/wallet/transactions?transaction_type=credit", headers=headers)
    assert response.status_code == status.HTTP_200_OK

def test_check_low_balance(client, db):
    """Test low balance check."""
    headers = get_auth_headers(client, "lowbalance@example.com")
    
    response = client.get("/api/v1/wallet/low-balance-check", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    assert "is_low" in response.json()

def test_get_grouped_transactions(client, db):
    """Test getting transactions grouped by case."""
    headers = get_auth_headers(client, "grouped@example.com")
    
    response = client.get("/api/v1/wallet/transactions/grouped", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    assert isinstance(response.json(), list)

def test_invalid_transaction_type(client, db):
    """Test invalid transaction type filter."""
    headers = get_auth_headers(client, "invalid@example.com")
    
    response = client.get("/api/v1/wallet/transactions?transaction_type=invalid", headers=headers)
    assert response.status_code == status.HTTP_400_BAD_REQUEST
