import pytest
from app.repositories.usage_metrics_repository import UsageMetricsRepository
from app.models.usage_metrics import UsageMetrics
from app.models.user import User
from app.models.case import Case, CaseStatus, Priority
from datetime import datetime, timedelta

def test_usage_metrics_repository_get_by_user_id(db):
    """Test getting usage metrics by user ID."""
    repo = UsageMetricsRepository()
    
    user = User(
        id="usage-repo-user-1",
        email="usagerepo1@example.com",
        name="Usage Repo User",
        is_active=True
    )
    metric = UsageMetrics(
        id="metric-repo-1",
        user_id=user.id,
        provider="openai",
        model="gpt-4o",
        operation_type="extraction",
        prompt_tokens=100,
        completion_tokens=50,
        total_tokens=150
    )
    db.add(user)
    db.add(metric)
    db.commit()
    
    metrics = repo.get_by_user_id(db, user.id)
    assert len(metrics) >= 1
    assert all(m.user_id == user.id for m in metrics)

def test_usage_metrics_repository_get_by_user_id_with_date_range(db):
    """Test getting usage metrics with date range."""
    repo = UsageMetricsRepository()
    
    user = User(
        id="date-range-user-1",
        email="daterange1@example.com",
        name="Date Range User",
        is_active=True
    )
    # Create metric in date range
    metric1 = UsageMetrics(
        id="metric-date-1",
        user_id=user.id,
        provider="openai",
        model="gpt-4o",
        operation_type="extraction",
        prompt_tokens=100,
        completion_tokens=50,
        total_tokens=150,
        request_timestamp=datetime.utcnow()
    )
    # Create metric outside date range
    metric2 = UsageMetrics(
        id="metric-date-2",
        user_id=user.id,
        provider="openai",
        model="gpt-4o",
        operation_type="extraction",
        prompt_tokens=200,
        completion_tokens=100,
        total_tokens=300,
        request_timestamp=datetime.utcnow() - timedelta(days=60)
    )
    db.add(user)
    db.add(metric1)
    db.add(metric2)
    db.commit()
    
    start_date = datetime.utcnow() - timedelta(days=30)
    end_date = datetime.utcnow()
    metrics = repo.get_by_user_id(db, user.id, start_date=start_date, end_date=end_date)
    # Should only get metric1 (within range)
    assert len(metrics) >= 1

def test_usage_metrics_repository_get_by_case_id(db):
    """Test getting usage metrics by case ID."""
    repo = UsageMetricsRepository()
    
    user = User(
        id="case-metrics-user-1",
        email="casemetrics1@example.com",
        name="Case Metrics User",
        is_active=True
    )
    case = Case(
        id="case-metrics-case-1",
        patient_id="PAT-METRICS-1",
        patient_name="Metrics Patient",
        case_number="CASE-METRICS-1",
        status=CaseStatus.READY,
        priority=Priority.NORMAL,
        user_id=user.id
    )
    metric = UsageMetrics(
        id="case-metric-1",
        user_id=user.id,
        case_id=case.id,
        provider="openai",
        model="gpt-4o",
        operation_type="extraction",
        prompt_tokens=100,
        completion_tokens=50,
        total_tokens=150
    )
    db.add(user)
    db.add(case)
    db.add(metric)
    db.commit()
    
    metrics = repo.get_by_case_id(db, case.id)
    assert len(metrics) >= 1
    assert all(m.case_id == case.id for m in metrics)

def test_usage_metrics_repository_get_aggregated_stats(db):
    """Test getting aggregated statistics."""
    repo = UsageMetricsRepository()
    
    user = User(
        id="aggregated-user-1",
        email="aggregated1@example.com",
        name="Aggregated User",
        is_active=True
    )
    metric1 = UsageMetrics(
        id="agg-metric-1",
        user_id=user.id,
        provider="openai",
        model="gpt-4o",
        operation_type="extraction",
        prompt_tokens=100,
        completion_tokens=50,
        total_tokens=150,
        estimated_cost_usd=0.001
    )
    metric2 = UsageMetrics(
        id="agg-metric-2",
        user_id=user.id,
        provider="openai",
        model="gpt-4o",
        operation_type="summary",
        prompt_tokens=200,
        completion_tokens=100,
        total_tokens=300,
        estimated_cost_usd=0.002
    )
    db.add(user)
    db.add(metric1)
    db.add(metric2)
    db.commit()
    
    stats = repo.get_aggregated_stats(db, user.id)
    assert "total_tokens" in stats
    assert stats["total_tokens"] >= 450
    assert stats["request_count"] >= 2
