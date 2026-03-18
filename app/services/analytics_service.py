"""Analytics service for ROI metrics tracking and calculation"""

import uuid
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional, Any, List
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, case as sql_case
from decimal import Decimal

from app.models.evidence_click import EvidenceClick
from app.models.case import Case, Priority
from app.repositories.evidence_click_repository import EvidenceClickRepository
from app.repositories.case_repository import CaseRepository
from app.repositories.case_file_repository import CaseFileRepository

logger = logging.getLogger(__name__)


class AnalyticsService:
    """Service for calculating ROI analytics metrics"""

    def __init__(self):
        self.evidence_click_repo = EvidenceClickRepository()
        self.case_repo = CaseRepository()
        self.case_file_repo = CaseFileRepository()

    def track_evidence_click(
        self,
        db: Session,
        user_id: str,
        case_id: str,
        entity_type: str,
        entity_id: str,
        source_type: str,
        file_id: Optional[str] = None,
        page_number: Optional[int] = None,
        chunk_id: Optional[str] = None,
    ) -> EvidenceClick:
        """
        Track an evidence click event

        Args:
            db: Database session
            user_id: User ID
            case_id: Case ID
            entity_type: Type of entity (timeline, medication, lab, diagnosis, chunk)
            entity_id: Entity identifier
            source_type: Source type (file or chunk)
            file_id: File ID if source_type is "file"
            page_number: Page number if source_type is "file"
            chunk_id: Chunk ID if source_type is "chunk"

        Returns:
            Created EvidenceClick record
        """
        try:
            click = EvidenceClick(
                id=str(uuid.uuid4()),
                user_id=user_id,
                case_id=case_id,
                entity_type=entity_type,
                entity_id=entity_id,
                source_type=source_type,
                file_id=file_id,
                page_number=page_number,
                chunk_id=chunk_id,
                clicked_at=datetime.utcnow()
            )
            return self.evidence_click_repo.create(db, click)
        except Exception as e:
            logger.error(f"Failed to track evidence click: {e}", exc_info=True)
            # Don't raise - tracking failures shouldn't break the app
            raise

    def get_time_to_review_metrics(
        self,
        db: Session,
        user_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        priority: Optional[Priority] = None
    ) -> Dict[str, Any]:
        """
        Calculate time-to-review metrics (avg, min, max, median)

        Args:
            db: Database session
            user_id: User ID
            start_date: Optional start date filter (filter by reviewed_at)
            end_date: Optional end date filter (filter by reviewed_at)
            priority: Optional priority filter

        Returns:
            Dictionary with average_hours, min_hours, max_hours, median_hours, total_cases
        """
        # Base query for reviewed cases
        query = db.query(Case).filter(
            and_(
                Case.user_id == user_id,
                Case.is_reviewed == True,
                Case.reviewed_at.isnot(None),
                Case.uploaded_at.isnot(None),
                # Ensure reviewed_at >= uploaded_at (data quality check)
                Case.reviewed_at >= Case.uploaded_at
            )
        )

        # Apply date range filter (on reviewed_at)
        if start_date:
            query = query.filter(Case.reviewed_at >= start_date)
        if end_date:
            query = query.filter(Case.reviewed_at <= end_date)

        # Apply priority filter
        if priority:
            query = query.filter(Case.priority == priority)

        # Calculate time difference in hours
        time_diff_hours = func.extract('epoch', Case.reviewed_at - Case.uploaded_at) / 3600.0

        # Get aggregated stats
        stats = query.with_entities(
            func.avg(time_diff_hours).label('avg_hours'),
            func.min(time_diff_hours).label('min_hours'),
            func.max(time_diff_hours).label('max_hours'),
            func.count(Case.id).label('total_cases')
        ).first()

        # Calculate median using percentile on hours (more reliable than interval)
        median_result = query.with_entities(
            func.percentile_cont(0.5).within_group(
                time_diff_hours.asc()
            ).label('median_hours')
        ).first()

        return {
            "average_hours": float(stats.avg_hours) if stats.avg_hours else 0.0,
            "min_hours": float(stats.min_hours) if stats.min_hours else 0.0,
            "max_hours": float(stats.max_hours) if stats.max_hours else 0.0,
            "median_hours": float(median_result.median_hours) if median_result and median_result.median_hours else 0.0,
            "total_cases": int(stats.total_cases) if stats.total_cases else 0
        }

    def get_cases_per_day(
        self,
        db: Session,
        user_id: str,
        start_date: datetime,
        end_date: datetime
    ) -> List[Dict[str, Any]]:
        """
        Get daily case counts (uploaded and reviewed)

        Args:
            db: Database session
            user_id: User ID
            start_date: Start date
            end_date: End date

        Returns:
            List of dictionaries with date, cases_reviewed, cases_uploaded
        """
        # Get cases reviewed per day
        reviewed_query = db.query(
            func.date(Case.reviewed_at).label('date'),
            func.count(Case.id).label('cases_reviewed')
        ).filter(
            and_(
                Case.user_id == user_id,
                Case.is_reviewed == True,
                Case.reviewed_at.isnot(None),
                Case.reviewed_at >= start_date,
                Case.reviewed_at <= end_date
            )
        ).group_by(func.date(Case.reviewed_at))

        reviewed_results = {r.date.isoformat(): r.cases_reviewed for r in reviewed_query.all()}

        # Get cases uploaded per day
        uploaded_query = db.query(
            func.date(Case.uploaded_at).label('date'),
            func.count(Case.id).label('cases_uploaded')
        ).filter(
            and_(
                Case.user_id == user_id,
                Case.uploaded_at >= start_date,
                Case.uploaded_at <= end_date
            )
        ).group_by(func.date(Case.uploaded_at))

        uploaded_results = {r.date.isoformat(): r.cases_uploaded for r in uploaded_query.all()}

        # Merge results by date
        all_dates = set(reviewed_results.keys()) | set(uploaded_results.keys())
        merged_results = []

        current_date = start_date.date()
        end_date_only = end_date.date()

        while current_date <= end_date_only:
            date_str = current_date.isoformat()
            merged_results.append({
                "date": date_str,
                "cases_reviewed": reviewed_results.get(date_str, 0),
                "cases_uploaded": uploaded_results.get(date_str, 0)
            })
            current_date += timedelta(days=1)

        return merged_results

    def get_evidence_click_stats(
        self,
        db: Session,
        user_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        case_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get evidence click statistics

        Args:
            db: Database session
            user_id: User ID
            start_date: Optional start date filter
            end_date: Optional end date filter
            case_id: Optional case ID filter

        Returns:
            Dictionary with total_clicks, by_type, by_case, time_series, recent_clicks
        """
        # Get counts by type
        by_type = self.evidence_click_repo.get_counts_by_type(
            db, user_id, start_date, end_date
        )

        # Get clicks by case (top cases)
        by_case = self.evidence_click_repo.get_clicks_by_case(
            db, user_id, start_date, end_date, limit=20
        )

        # Get case numbers for the top cases
        case_ids = [item["case_id"] for item in by_case]
        case_numbers_map = {}
        if case_ids:
            cases = db.query(Case.id, Case.case_number).filter(
                Case.id.in_(case_ids)
            ).all()
            case_numbers_map = {case.id: case.case_number for case in cases}

        # Add case numbers to by_case results
        for item in by_case:
            item["case_number"] = case_numbers_map.get(item["case_id"], "Unknown")

        # Get time series data
        if start_date and end_date:
            time_series = self.evidence_click_repo.get_time_series(
                db, user_id, start_date, end_date, group_by="day"
            )
        else:
            time_series = []

        # Get recent clicks
        recent_clicks = self.evidence_click_repo.get_recent_clicks(db, user_id, limit=10)

        # Format recent clicks
        recent_clicks_formatted = []
        for click in recent_clicks:
            case = self.case_repo.get_by_id(db, click.case_id)
            recent_clicks_formatted.append({
                "id": click.id,
                "case_id": click.case_id,
                "case_number": case.case_number if case else "Unknown",
                "entity_type": click.entity_type,
                "entity_id": click.entity_id,
                "source_type": click.source_type,
                "clicked_at": click.clicked_at.isoformat() if click.clicked_at else None
            })

        # Calculate total clicks
        total_clicks = sum(by_type.values())

        return {
            "total_clicks": total_clicks,
            "by_type": by_type,
            "by_case": by_case,
            "time_series": time_series,
            "recent_clicks": recent_clicks_formatted
        }

    def get_summary_metrics(
        self,
        db: Session,
        user_id: str,
        start_date: datetime,
        end_date: datetime
    ) -> Dict[str, Any]:
        """
        Get comprehensive summary metrics for dashboard

        Args:
            db: Database session
            user_id: User ID
            start_date: Start date
            end_date: End date

        Returns:
            Dictionary with all metrics combined
        """
        # Time-to-review metrics
        time_to_review = self.get_time_to_review_metrics(db, user_id, start_date, end_date)

        # Cases per day
        cases_per_day = self.get_cases_per_day(db, user_id, start_date, end_date)

        # Evidence clicks
        evidence_clicks = self.get_evidence_click_stats(db, user_id, start_date, end_date)

        # Calculate today's cases reviewed
        today = datetime.utcnow().date()
        today_cases = db.query(Case).filter(
            and_(
                Case.user_id == user_id,
                Case.is_reviewed == True,
                Case.reviewed_at.isnot(None),
                func.date(Case.reviewed_at) == today
            )
        ).count()

        return {
            "time_to_review": time_to_review,
            "cases_per_day": cases_per_day,
            "evidence_clicks": evidence_clicks,
            "today_cases_reviewed": today_cases,
            "date_range": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat()
            }
        }

