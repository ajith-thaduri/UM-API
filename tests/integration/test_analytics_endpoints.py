"""Integration tests for Analytics API endpoints"""

import pytest
import uuid
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
from fastapi import status
from app.models.user import User
from app.models.case import Case, CaseStatus, Priority


def get_auth_headers(client, email="analytics@example.com", password="password123"):
    """Helper to register and get auth token."""
    reg_data = {"email": email, "password": password, "name": "Test User"}
    response = client.post("/api/v1/auth/register", json=reg_data)
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@patch("app.services.analytics_service.AnalyticsService.get_summary_metrics")
def test_get_review_metrics(mock_get_summary, client, db):
    """Test getting comprehensive review metrics"""
    headers = get_auth_headers(client, "reviewmetrics@example.com")
    
    # Mock analytics service return value that matches the expected dict structure
    mock_get_summary.return_value = {
        "time_to_review": {
            "average_hours": 24.5,
            "min_hours": 1.0,
            "max_hours": 48.0,
            "median_hours": 20.0,
            "total_cases": 10
        },
        "cases_per_day": [
            {"date": "2024-01-01", "cases_reviewed": 5, "cases_uploaded": 10}
        ],
        "evidence_clicks": {
            "total_clicks": 100,
            "by_type": {"medication": 50, "lab": 30, "diagnosis": 20},
            "by_case": [],
            "time_series": [],
            "recent_clicks": []
        },
        "today_cases_reviewed": 2,
        "date_range": {"start": "2024-01-01", "end": "2024-01-31"}
    }
    
    response = client.get("/api/v1/analytics/review-metrics", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "time_to_review" in data


def test_get_review_metrics_with_date_range(client, db):
    """Test getting review metrics with date range"""
    headers = get_auth_headers(client, "reviewmetricsdate@example.com")
    
    start_date = (datetime.utcnow() - timedelta(days=30)).isoformat()
    end_date = datetime.utcnow().isoformat()
    
    response = client.get(
        f"/api/v1/analytics/review-metrics?start_date={start_date}&end_date={end_date}",
        headers=headers
    )
    assert response.status_code == status.HTTP_200_OK


def test_get_review_metrics_invalid_date_range(client, db):
    """Test getting review metrics with invalid date range"""
    headers = get_auth_headers(client, "reviewmetricsinvalid@example.com")
    
    start_date = datetime.utcnow().isoformat()
    end_date = (datetime.utcnow() - timedelta(days=30)).isoformat()  # End before start
    
    response = client.get(
        f"/api/v1/analytics/review-metrics?start_date={start_date}&end_date={end_date}",
        headers=headers
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@patch("app.services.analytics_service.AnalyticsService.get_time_to_review_metrics")
def test_get_time_to_review(mock_get_time, client, db):
    """Test getting time-to-review metrics"""
    headers = get_auth_headers(client, "timetoreview@example.com")
    
    # Mock analytics service
    mock_get_time.return_value = {
        "average_hours": 24.5,
        "min_hours": 1.0,
        "max_hours": 48.0,
        "median_hours": 20.0,
        "total_cases": 10
    }
    
    response = client.get("/api/v1/analytics/time-to-review", headers=headers)
    assert response.status_code == status.HTTP_200_OK


@patch("app.services.analytics_service.AnalyticsService.get_cases_per_day")
def test_get_cases_per_day(mock_get_cases, client, db):
    """Test getting cases per day statistics"""
    headers = get_auth_headers(client, "casesperday@example.com")
    
    # Mock analytics service
    mock_get_cases.return_value = [
        {"date": "2024-01-01", "cases_reviewed": 5, "cases_uploaded": 10}
    ]
    
    response = client.get("/api/v1/analytics/cases-per-day", headers=headers)
    assert response.status_code == status.HTTP_200_OK


@patch("app.services.analytics_service.AnalyticsService.get_evidence_click_stats")
def test_get_evidence_clicks(mock_get_clicks, client, db):
    """Test getting evidence click statistics"""
    headers = get_auth_headers(client, "evidenceclicks@example.com")
    
    # Mock analytics service
    mock_get_clicks.return_value = {
        "total_clicks": 100,
        "by_type": {"medication": 50},
        "by_case": [],
        "time_series": [],
        "recent_clicks": []
    }
    
    response = client.get("/api/v1/analytics/evidence-clicks", headers=headers)
    assert response.status_code == status.HTTP_200_OK
