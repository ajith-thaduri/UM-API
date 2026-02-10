import pytest
from app.services.usage_tracking_service import UsageTrackingService
from app.models.usage_metrics import UsageMetrics
from app.models.user import User
from decimal import Decimal

def test_calculate_cost_openai(db):
    """Test cost calculation for OpenAI models."""
    service = UsageTrackingService()
    
    cost = service.calculate_cost("openai", "gpt-4o", 1000, 500)
    assert cost is not None
    assert cost > 0

def test_calculate_cost_claude(db):
    """Test cost calculation for Claude models."""
    service = UsageTrackingService()
    
    cost = service.calculate_cost("claude", "claude-haiku-4-5", 1000, 500)
    assert cost is not None
    assert cost > 0

def test_calculate_cost_unknown_model(db):
    """Test cost calculation for unknown model."""
    service = UsageTrackingService()
    
    cost = service.calculate_cost("openai", "unknown-model", 1000, 500)
    # Should return None for unknown models
    assert cost is None

def test_track_llm_usage(db):
    """Test tracking LLM usage metrics."""
    service = UsageTrackingService()
    
    user = User(
        id="usage-track-user-1",
        email="usagetrack1@example.com",
        name="Usage Track User",
        is_active=True
    )
    db.add(user)
    db.commit()
    
    metric = service.track_llm_usage(
        db=db,
        user_id=user.id,
        provider="openai",
        model="gpt-4o",
        operation_type="extraction",
        prompt_tokens=100,
        completion_tokens=50,
        total_tokens=150,
        case_id=None
    )
    
    assert metric is not None
    assert metric.total_tokens == 150

def test_get_user_usage(db):
    """Test getting user usage statistics."""
    service = UsageTrackingService()
    
    user = User(
        id="user-usage-1",
        email="userusage1@example.com",
        name="User Usage",
        is_active=True
    )
    db.add(user)
    db.commit()
    
    # Create usage metrics
    metric1 = UsageMetrics(
        id="metric-1",
        user_id=user.id,
        provider="openai",
        model="gpt-4o",
        operation_type="extraction",
        prompt_tokens=100,
        completion_tokens=50,
        total_tokens=150
    )
    metric2 = UsageMetrics(
        id="metric-2",
        user_id=user.id,
        provider="openai",
        model="gpt-4o",
        operation_type="summary",
        prompt_tokens=200,
        completion_tokens=100,
        total_tokens=300
    )
    db.add(metric1)
    db.add(metric2)
    db.commit()
    
    from datetime import datetime, timedelta
    stats = service.get_user_usage(
        db=db,
        user_id=user.id,
        start_date=datetime.utcnow() - timedelta(days=30),
        end_date=datetime.utcnow()
    )
    
    assert "total_tokens" in stats
    assert stats["total_tokens"] >= 450
