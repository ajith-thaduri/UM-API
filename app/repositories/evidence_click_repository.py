"""Evidence click repository"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, desc

from app.repositories.base import BaseRepository
from app.models.evidence_click import EvidenceClick


class EvidenceClickRepository(BaseRepository[EvidenceClick]):
    """Repository for EvidenceClick model"""

    def __init__(self):
        super().__init__(EvidenceClick)

    def get_by_case(
        self,
        db: Session,
        case_id: str,
        user_id: Optional[str] = None,
        limit: int = 100
    ) -> List[EvidenceClick]:
        """
        Get all clicks for a specific case

        Args:
            db: Database session
            case_id: Case ID
            user_id: Optional user ID to filter by
            limit: Maximum number of records to return

        Returns:
            List of EvidenceClick records
        """
        query = db.query(EvidenceClick).filter(EvidenceClick.case_id == case_id)
        
        if user_id:
            query = query.filter(EvidenceClick.user_id == user_id)
        
        return query.order_by(desc(EvidenceClick.clicked_at)).limit(limit).all()

    def get_counts_by_type(
        self,
        db: Session,
        user_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, int]:
        """
        Get click counts aggregated by entity_type

        Args:
            db: Database session
            user_id: User ID
            start_date: Optional start date filter
            end_date: Optional end date filter

        Returns:
            Dictionary mapping entity_type to count
        """
        query = db.query(
            EvidenceClick.entity_type,
            func.count(EvidenceClick.id).label('count')
        ).filter(EvidenceClick.user_id == user_id)
        
        if start_date:
            query = query.filter(EvidenceClick.clicked_at >= start_date)
        if end_date:
            query = query.filter(EvidenceClick.clicked_at <= end_date)
        
        results = query.group_by(EvidenceClick.entity_type).all()
        
        return {r.entity_type: r.count for r in results}

    def get_clicks_by_case(
        self,
        db: Session,
        user_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Get click counts grouped by case

        Args:
            db: Database session
            user_id: User ID
            start_date: Optional start date filter
            end_date: Optional end date filter
            limit: Maximum number of cases to return

        Returns:
            List of dictionaries with case_id and click count
        """
        query = db.query(
            EvidenceClick.case_id,
            func.count(EvidenceClick.id).label('clicks')
        ).filter(EvidenceClick.user_id == user_id)
        
        if start_date:
            query = query.filter(EvidenceClick.clicked_at >= start_date)
        if end_date:
            query = query.filter(EvidenceClick.clicked_at <= end_date)
        
        results = query.group_by(EvidenceClick.case_id)\
            .order_by(desc('clicks'))\
            .limit(limit).all()
        
        return [
            {
                "case_id": r.case_id,
                "clicks": r.clicks
            }
            for r in results
        ]

    def get_time_series(
        self,
        db: Session,
        user_id: str,
        start_date: datetime,
        end_date: datetime,
        group_by: str = "day"
    ) -> List[Dict[str, Any]]:
        """
        Get time-series data for evidence clicks

        Args:
            db: Database session
            user_id: User ID
            start_date: Start date
            end_date: End date
            group_by: Grouping interval (day/week/month)

        Returns:
            List of dictionaries with date and click count
        """
        # Determine date truncation based on group_by
        if group_by == "day":
            date_trunc = func.date_trunc('day', EvidenceClick.clicked_at)
        elif group_by == "week":
            date_trunc = func.date_trunc('week', EvidenceClick.clicked_at)
        elif group_by == "month":
            date_trunc = func.date_trunc('month', EvidenceClick.clicked_at)
        else:
            date_trunc = func.date_trunc('day', EvidenceClick.clicked_at)
        
        query = db.query(
            date_trunc.label('date'),
            func.count(EvidenceClick.id).label('clicks')
        ).filter(
            and_(
                EvidenceClick.user_id == user_id,
                EvidenceClick.clicked_at >= start_date,
                EvidenceClick.clicked_at <= end_date
            )
        ).group_by(date_trunc).order_by(date_trunc)
        
        results = query.all()
        
        return [
            {
                "date": r.date.date().isoformat() if r.date else None,
                "clicks": r.clicks
            }
            for r in results
        ]

    def get_recent_clicks(
        self,
        db: Session,
        user_id: str,
        limit: int = 20
    ) -> List[EvidenceClick]:
        """
        Get recent evidence clicks for a user

        Args:
            db: Database session
            user_id: User ID
            limit: Maximum number of records to return

        Returns:
            List of EvidenceClick records ordered by clicked_at descending
        """
        return (
            db.query(EvidenceClick)
            .filter(EvidenceClick.user_id == user_id)
            .order_by(desc(EvidenceClick.clicked_at))
            .limit(limit)
            .all()
        )

