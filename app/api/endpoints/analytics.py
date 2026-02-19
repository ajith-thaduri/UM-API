"""Analytics API endpoints for ROI metrics"""

from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.api.endpoints.auth import get_current_user
from app.models.user import User
from app.models.case import Priority
from app.services.analytics_service import AnalyticsService
from app.schemas.analytics import (
    ReviewMetricsResponse,
    TimeToReviewResponse,
    CasesPerDayResponse,
    EvidenceClicksResponse,
    TimeToReviewMetrics,
    EvidenceClickStats,
)

router = APIRouter()


def get_analytics_service() -> AnalyticsService:
    """Dependency for AnalyticsService"""
    return AnalyticsService()


@router.get("/analytics/review-metrics", response_model=ReviewMetricsResponse)
async def get_review_metrics(
    start_date: Optional[datetime] = Query(None, description="Start date (ISO format)"),
    end_date: Optional[datetime] = Query(None, description="End date (ISO format)"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    analytics_service: AnalyticsService = Depends(get_analytics_service),
):
    """
    Get comprehensive review metrics (time-to-review, cases per day, evidence clicks)
    
    Returns all analytics metrics in a single call for dashboard display.
    """
    # Default to last 30 days if no dates provided
    if not end_date:
        end_date = datetime.utcnow()
    if not start_date:
        start_date = end_date - timedelta(days=30)
    
    if end_date < start_date:
        raise HTTPException(status_code=400, detail="end_date must be after start_date")
    
    try:
        summary = analytics_service.get_summary_metrics(
            db=db,
            user_id=current_user.id,
            start_date=start_date,
            end_date=end_date
        )
        
        return ReviewMetricsResponse(
            time_to_review=TimeToReviewMetrics(**summary["time_to_review"]),
            cases_per_day=summary["cases_per_day"],
            evidence_clicks=EvidenceClickStats(
                total_clicks=summary["evidence_clicks"]["total_clicks"],
                by_type=summary["evidence_clicks"]["by_type"],
                by_case=summary["evidence_clicks"]["by_case"],
                time_series=summary["evidence_clicks"]["time_series"],
                recent_clicks=summary["evidence_clicks"]["recent_clicks"]
            ),
            today_cases_reviewed=summary["today_cases_reviewed"],
            date_range=summary["date_range"]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch review metrics: {str(e)}")


@router.get("/analytics/time-to-review", response_model=TimeToReviewResponse)
async def get_time_to_review(
    start_date: Optional[datetime] = Query(None, description="Start date (ISO format)"),
    end_date: Optional[datetime] = Query(None, description="End date (ISO format)"),
    priority: Optional[str] = Query(None, description="Filter by priority (urgent, high, normal, low)"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    analytics_service: AnalyticsService = Depends(get_analytics_service),
):
    """
    Get detailed time-to-review metrics
    
    Returns average, min, max, and median time-to-review in hours.
    """
    # Default to last 30 days if no dates provided
    if not end_date:
        end_date = datetime.utcnow()
    if not start_date:
        start_date = end_date - timedelta(days=30)
    
    if end_date < start_date:
        raise HTTPException(status_code=400, detail="end_date must be after start_date")
    
    # Parse priority if provided
    priority_enum = None
    if priority:
        try:
            priority_enum = Priority(priority.lower())
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid priority: {priority}. Must be one of: urgent, high, normal, low")
    
    try:
        metrics = analytics_service.get_time_to_review_metrics(
            db=db,
            user_id=current_user.id,
            start_date=start_date,
            end_date=end_date,
            priority=priority_enum
        )
        
        return TimeToReviewResponse(
            metrics=TimeToReviewMetrics(**metrics),
            date_range={
                "start": start_date.isoformat(),
                "end": end_date.isoformat()
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch time-to-review metrics: {str(e)}")


@router.get("/analytics/cases-per-day", response_model=CasesPerDayResponse)
async def get_cases_per_day(
    start_date: Optional[datetime] = Query(None, description="Start date (ISO format)"),
    end_date: Optional[datetime] = Query(None, description="End date (ISO format)"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    analytics_service: AnalyticsService = Depends(get_analytics_service),
):
    """
    Get daily case throughput metrics
    
    Returns cases uploaded and cases reviewed per day in the specified date range.
    """
    # Default to last 30 days if no dates provided
    if not end_date:
        end_date = datetime.utcnow()
    if not start_date:
        start_date = end_date - timedelta(days=30)
    
    if end_date < start_date:
        raise HTTPException(status_code=400, detail="end_date must be after start_date")
    
    try:
        data = analytics_service.get_cases_per_day(
            db=db,
            user_id=current_user.id,
            start_date=start_date,
            end_date=end_date
        )
        
        return CasesPerDayResponse(
            data=data,
            date_range={
                "start": start_date.isoformat(),
                "end": end_date.isoformat()
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch cases per day: {str(e)}")


@router.get("/analytics/evidence-clicks", response_model=EvidenceClicksResponse)
async def get_evidence_clicks(
    start_date: Optional[datetime] = Query(None, description="Start date (ISO format)"),
    end_date: Optional[datetime] = Query(None, description="End date (ISO format)"),
    case_id: Optional[str] = Query(None, description="Filter by case ID"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    analytics_service: AnalyticsService = Depends(get_analytics_service),
):
    """
    Get evidence click statistics
    
    Returns total clicks, breakdown by entity type, top cases by clicks, and time-series data.
    """
    # Default to last 30 days if no dates provided
    if not end_date:
        end_date = datetime.utcnow()
    if not start_date:
        start_date = end_date - timedelta(days=30)
    
    if end_date < start_date:
        raise HTTPException(status_code=400, detail="end_date must be after start_date")
    
    try:
        stats = analytics_service.get_evidence_click_stats(
            db=db,
            user_id=current_user.id,
            start_date=start_date,
            end_date=end_date,
            case_id=case_id
        )
        
        return EvidenceClicksResponse(
            stats=EvidenceClickStats(
                total_clicks=stats["total_clicks"],
                by_type=stats["by_type"],
                by_case=stats["by_case"],
                time_series=stats["time_series"],
                recent_clicks=stats["recent_clicks"]
            ),
            date_range={
                "start": start_date.isoformat(),
                "end": end_date.isoformat()
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch evidence click stats: {str(e)}")

