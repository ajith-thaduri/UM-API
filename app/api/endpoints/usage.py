"""Usage tracking API endpoints"""

from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.db.session import get_db
from app.api.endpoints.auth import get_current_user
from app.models.user import User
from app.services.usage_tracking_service import usage_tracking_service

router = APIRouter()


class UsageStatsResponse(BaseModel):
    total_tokens: int
    prompt_tokens: int
    completion_tokens: int
    total_cost: float
    request_count: int


class UsageByProviderResponse(BaseModel):
    provider: str
    model: str
    total_tokens: int
    total_cost: float
    request_count: int


class TimeSeriesDataPoint(BaseModel):
    period: str
    total_tokens: int
    total_cost: float
    request_count: int


class UsageTimeSeriesResponse(BaseModel):
    data: List[TimeSeriesDataPoint]


@router.get("/usage/stats", response_model=UsageStatsResponse)
async def get_usage_stats(
    start_date: Optional[datetime] = Query(None, description="Start date (ISO format)"),
    end_date: Optional[datetime] = Query(None, description="End date (ISO format)"),
    provider: Optional[str] = Query(None, description="Filter by provider"),
    model: Optional[str] = Query(None, description="Filter by model"),
    operation_type: Optional[str] = Query(None, description="Filter by operation type"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get aggregated usage statistics for the current user"""
    # Default to last 30 days if no dates provided
    if not end_date:
        end_date = datetime.utcnow()
    if not start_date:
        start_date = end_date - timedelta(days=30)
    
    stats = usage_tracking_service.get_user_usage(
        db=db,
        user_id=current_user.id,
        start_date=start_date,
        end_date=end_date
    )
    
    # Apply additional filters if provided (would need to extend repository for this)
    # For now, return aggregated stats
    
    return stats


@router.get("/usage/by-provider", response_model=List[UsageByProviderResponse])
async def get_usage_by_provider(
    start_date: Optional[datetime] = Query(None, description="Start date (ISO format)"),
    end_date: Optional[datetime] = Query(None, description="End date (ISO format)"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get usage breakdown by provider and model"""
    # Default to last 30 days if no dates provided
    if not end_date:
        end_date = datetime.utcnow()
    if not start_date:
        start_date = end_date - timedelta(days=30)
    
    breakdown = usage_tracking_service.get_usage_by_provider(
        db=db,
        user_id=current_user.id,
        start_date=start_date,
        end_date=end_date
    )
    
    return [
        UsageByProviderResponse(**item)
        for item in breakdown
    ]


@router.get("/usage/by-case/{case_id}", response_model=Dict[str, Any])
async def get_case_usage(
    case_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get usage statistics for a specific case"""
    # Verify case belongs to user (would need case repository check)
    # For now, just return usage
    
    usage = usage_tracking_service.get_case_usage(db=db, case_id=case_id)
    
    return usage


@router.get("/usage/time-series", response_model=UsageTimeSeriesResponse)
async def get_usage_time_series(
    start_date: datetime = Query(..., description="Start date (ISO format)"),
    end_date: datetime = Query(..., description="End date (ISO format)"),
    group_by: str = Query("day", description="Grouping interval: day, week, or month"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get time-series usage data for charts"""
    if group_by not in ["day", "week", "month"]:
        raise HTTPException(status_code=400, detail="group_by must be 'day', 'week', or 'month'")
    
    if end_date < start_date:
        raise HTTPException(status_code=400, detail="end_date must be after start_date")
    
    time_series = usage_tracking_service.get_time_series(
        db=db,
        user_id=current_user.id,
        start_date=start_date,
        end_date=end_date,
        group_by=group_by
    )
    
    return {
        "data": [
            TimeSeriesDataPoint(**item)
            for item in time_series
        ]
    }

