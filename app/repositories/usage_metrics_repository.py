"""Usage metrics repository"""

from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_

from app.repositories.base import BaseRepository
from app.models.usage_metrics import UsageMetrics


class UsageMetricsRepository(BaseRepository[UsageMetrics]):
    """Repository for UsageMetrics model"""

    def __init__(self):
        super().__init__(UsageMetrics)

    def get_by_user_id(
        self,
        db: Session,
        user_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        skip: int = 0,
        limit: int = 100
    ) -> List[UsageMetrics]:
        """
        Get usage metrics for a user with optional date range

        Args:
            db: Database session
            user_id: User ID
            start_date: Optional start date filter
            end_date: Optional end date filter
            skip: Number of records to skip
            limit: Maximum number of records

        Returns:
            List of UsageMetrics
        """
        query = db.query(UsageMetrics).filter(UsageMetrics.user_id == user_id)
        
        if start_date:
            query = query.filter(UsageMetrics.request_timestamp >= start_date)
        if end_date:
            query = query.filter(UsageMetrics.request_timestamp <= end_date)
        
        return query.order_by(UsageMetrics.request_timestamp.desc()).offset(skip).limit(limit).all()

    def get_by_prompt_id(
        self,
        db: Session,
        prompt_id: str,
        skip: int = 0,
        limit: int = 100
    ) -> List[UsageMetrics]:
        """
        Get usage metrics filtered by prompt_id in extra_metadata

        Args:
            db: Database session
            prompt_id: The ID of the prompt
            skip: Number of records to skip
            limit: Maximum number of records

        Returns:
            List of UsageMetrics
        """
        from sqlalchemy import text
        return (
            db.query(UsageMetrics)
            .filter(UsageMetrics.extra_metadata.op("->>")("prompt_id") == prompt_id)
            .order_by(UsageMetrics.request_timestamp.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def get_by_case_id(self, db: Session, case_id: str) -> List[UsageMetrics]:
        """
        Get usage metrics for a specific case

        Args:
            db: Database session
            case_id: Case ID

        Returns:
            List of UsageMetrics
        """
        return (
            db.query(UsageMetrics)
            .filter(UsageMetrics.case_id == case_id)
            .order_by(UsageMetrics.request_timestamp.desc())
            .all()
        )

    def get_aggregated_stats(
        self,
        db: Session,
        user_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Get aggregated usage statistics for a user

        Args:
            db: Database session
            user_id: User ID
            start_date: Optional start date filter
            end_date: Optional end date filter

        Returns:
            Dictionary with aggregated stats
        """
        query = db.query(
            func.sum(UsageMetrics.total_tokens).label('total_tokens'),
            func.sum(UsageMetrics.prompt_tokens).label('prompt_tokens'),
            func.sum(UsageMetrics.completion_tokens).label('completion_tokens'),
            func.sum(UsageMetrics.estimated_cost_usd).label('total_cost'),
            func.count(UsageMetrics.id).label('request_count')
        ).filter(UsageMetrics.user_id == user_id)
        
        if start_date:
            query = query.filter(UsageMetrics.request_timestamp >= start_date)
        if end_date:
            query = query.filter(UsageMetrics.request_timestamp <= end_date)
        
        result = query.first()
        
        return {
            "total_tokens": int(result.total_tokens or 0),
            "prompt_tokens": int(result.prompt_tokens or 0),
            "completion_tokens": int(result.completion_tokens or 0),
            "total_cost": float(result.total_cost or 0.0),
            "request_count": int(result.request_count or 0)
        }

    def get_by_provider_model(
        self,
        db: Session,
        user_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """
        Get usage breakdown by provider and model

        Args:
            db: Database session
            user_id: User ID
            start_date: Optional start date filter
            end_date: Optional end date filter

        Returns:
            List of dictionaries with provider, model, and aggregated stats
        """
        query = db.query(
            UsageMetrics.provider,
            UsageMetrics.model,
            func.sum(UsageMetrics.total_tokens).label('total_tokens'),
            func.sum(UsageMetrics.estimated_cost_usd).label('total_cost'),
            func.count(UsageMetrics.id).label('request_count')
        ).filter(UsageMetrics.user_id == user_id)
        
        if start_date:
            query = query.filter(UsageMetrics.request_timestamp >= start_date)
        if end_date:
            query = query.filter(UsageMetrics.request_timestamp <= end_date)
        
        results = query.group_by(UsageMetrics.provider, UsageMetrics.model).all()
        
        return [
            {
                "provider": r.provider,
                "model": r.model,
                "total_tokens": int(r.total_tokens or 0),
                "total_cost": float(r.total_cost or 0.0),
                "request_count": int(r.request_count or 0)
            }
            for r in results
        ]

    def get_time_series(
        self,
        db: Session,
        user_id: str,
        start_date: datetime,
        end_date: datetime,
        group_by: str = "day"  # "day", "week", "month"
    ) -> List[Dict[str, Any]]:
        """
        Get time-series data for usage metrics

        Args:
            db: Database session
            user_id: User ID
            start_date: Start date
            end_date: End date
            group_by: Grouping interval (day/week/month)

        Returns:
            List of dictionaries with date and aggregated stats
        """
        # Determine date truncation based on group_by
        if group_by == "day":
            date_trunc = func.date_trunc('day', UsageMetrics.request_timestamp)
        elif group_by == "week":
            date_trunc = func.date_trunc('week', UsageMetrics.request_timestamp)
        elif group_by == "month":
            date_trunc = func.date_trunc('month', UsageMetrics.request_timestamp)
        else:
            date_trunc = func.date_trunc('day', UsageMetrics.request_timestamp)
        
        query = db.query(
            date_trunc.label('period'),
            func.sum(UsageMetrics.total_tokens).label('total_tokens'),
            func.sum(UsageMetrics.estimated_cost_usd).label('total_cost'),
            func.count(UsageMetrics.id).label('request_count')
        ).filter(
            and_(
                UsageMetrics.user_id == user_id,
                UsageMetrics.request_timestamp >= start_date,
                UsageMetrics.request_timestamp <= end_date
            )
        ).group_by(date_trunc).order_by(date_trunc)
        
        results = query.all()
        
        return [
            {
                "period": r.period.isoformat() if r.period else None,
                "total_tokens": int(r.total_tokens or 0),
                "total_cost": float(r.total_cost or 0.0),
                "request_count": int(r.request_count or 0)
            }
            for r in results
        ]

