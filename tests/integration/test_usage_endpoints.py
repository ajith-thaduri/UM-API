import pytest
from fastapi import status
from datetime import datetime, timedelta
from app.models.user import User
from app.models.usage_metrics import UsageMetrics

def get_auth_headers(client, email="usage@example.com", password="password123"):
    """Helper to register and get auth token."""
    reg_data = {"email": email, "password": password, "name": "Test User"}
    response = client.post("/api/v1/auth/register", json=reg_data)
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}

def test_get_usage_stats(client, db):
    """Test getting usage statistics."""
    headers = get_auth_headers(client, "usagestats@example.com")
    
    # Create some usage metrics
    user = db.query(User).filter(User.email == "usagestats@example.com").first()
    
    metric = UsageMetrics(
        id="usage-1",
        user_id=user.id,
        provider="openai",
        model="gpt-4o",
        operation_type="extraction",
        prompt_tokens=100,
        completion_tokens=50,
        total_tokens=150,
        estimated_cost_usd=0.001
    )
    db.add(metric)
    db.commit()
    
    response = client.get("/api/v1/usage/stats", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    assert "total_tokens" in response.json()

def test_get_usage_by_provider(client, db):
    """Test getting usage by provider."""
    headers = get_auth_headers(client, "usageprovider@example.com")
    
    user = db.query(User).filter(User.email == "usageprovider@example.com").first()
    
    metric = UsageMetrics(
        id="usage-provider-1",
        user_id=user.id,
        provider="openai",
        model="gpt-4o",
        operation_type="extraction",
        prompt_tokens=200,
        completion_tokens=100,
        total_tokens=300
    )
    db.add(metric)
    db.commit()
    
    response = client.get("/api/v1/usage/by-provider", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    assert isinstance(response.json(), list)

def test_get_usage_time_series(client, db):
    """Test getting usage time series."""
    headers = get_auth_headers(client, "timeseries@example.com")
    
    start_date = (datetime.utcnow() - timedelta(days=7)).isoformat()
    end_date = datetime.utcnow().isoformat()
    
    response = client.get(
        f"/api/v1/usage/time-series?start_date={start_date}&end_date={end_date}&group_by=day",
        headers=headers
    )
    assert response.status_code == status.HTTP_200_OK
    assert "data" in response.json()

def test_get_usage_time_series_invalid_group_by(client, db):
    """Test time series with invalid group_by."""
    headers = get_auth_headers(client, "invalidgroup@example.com")
    
    start_date = (datetime.utcnow() - timedelta(days=7)).isoformat()
    end_date = datetime.utcnow().isoformat()
    
    response = client.get(
        f"/api/v1/usage/time-series?start_date={start_date}&end_date={end_date}&group_by=invalid",
        headers=headers
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST

def test_get_usage_time_series_invalid_dates(client, db):
    """Test time series with invalid date range."""
    headers = get_auth_headers(client, "invaliddates@example.com")
    
    start_date = datetime.utcnow().isoformat()
    end_date = (datetime.utcnow() - timedelta(days=7)).isoformat()  # End before start
    
    response = client.get(
        f"/api/v1/usage/time-series?start_date={start_date}&end_date={end_date}&group_by=day",
        headers=headers
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
