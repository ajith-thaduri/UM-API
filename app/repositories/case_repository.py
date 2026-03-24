"""Case repository"""

from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import and_, func, case as sql_case, cast, String
from datetime import datetime
import json

from app.repositories.base import BaseRepository
from app.models.case import Case, CaseStatus, Priority


class CaseRepository(BaseRepository[Case]):
    """Repository for Case model"""

    def __init__(self):
        super().__init__(Case)

    def get_by_id(self, db: Session, id: str, user_id: Optional[str] = None) -> Optional[Case]:
        """
        Get case by ID, optionally filtered by user_id
        """
        from sqlalchemy.orm import selectinload, joinedload
        from app.models.case_version import CaseVersion
        query = db.query(Case).filter(Case.id == id).options(
            selectinload(Case.files),
            joinedload(Case.live_version).joinedload(CaseVersion.clinical_extraction),
        )
        if user_id:
            query = query.filter(Case.user_id == user_id)
        return query.first()

    def get_by_case_number(self, db: Session, case_number: str, user_id: str) -> Optional[Case]:
        """
        Get case by case number for a specific user
        """
        from sqlalchemy.orm import selectinload, joinedload
        from app.models.case_version import CaseVersion
        return db.query(Case).filter(
            and_(Case.case_number == case_number, Case.user_id == user_id)
        ).options(
            selectinload(Case.files),
            joinedload(Case.live_version).joinedload(CaseVersion.clinical_extraction),
        ).first()

    def get_by_status(
        self,
        db: Session,
        status: CaseStatus,
        user_id: str,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Case]:
        """
        Get cases by status for a specific user
        """
        from sqlalchemy.orm import selectinload
        return (
            db.query(Case)
            .filter(and_(Case.status == status, Case.user_id == user_id))
            .options(selectinload(Case.files))
            .order_by(Case.uploaded_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def get_by_priority(
        self,
        db: Session,
        priority: Priority,
        user_id: str,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Case]:
        """
        Get cases by priority for a specific user
        """
        from sqlalchemy.orm import selectinload
        return (
            db.query(Case)
            .filter(and_(Case.priority == priority, Case.user_id == user_id))
            .options(selectinload(Case.files))
            .order_by(Case.uploaded_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def get_with_filters(
        self,
        db: Session,
        user_id: str,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        search: Optional[str] = None,
        date_range: Optional[str] = None,
        sort_by: str = "uploaded_at",
        sort_order: str = "desc",
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[List[Case], int]:
        """
        Get cases with filters, sorting, and pagination for a specific user.
        Includes optimized eager loading.
        """
        from sqlalchemy.orm import selectinload, joinedload
        from app.models.case_version import CaseVersion
        
        # Start with eager loading options
        query = db.query(Case).options(
            selectinload(Case.files),
            joinedload(Case.live_version).joinedload(CaseVersion.clinical_extraction),
        ).filter(Case.user_id == user_id)

        # Apply filters
        if status:
            query = query.filter(Case.status == status)
        if priority:
            query = query.filter(Case.priority == priority)
        
        if search:
            search_filter = f"%{search}%"
            # Basic text filters
            text_filters = (
                (Case.patient_name.ilike(search_filter)) | 
                (Case.case_number.ilike(search_filter)) |
                (Case.patient_id.ilike(search_filter))
            )
            
            # Try to see if search term might be a date part
            date_filter = cast(Case.uploaded_at, String).ilike(search_filter)
            
            query = query.filter(text_filters | date_filter)

        if date_range and date_range != "all":
            from datetime import timedelta, date
            today = date.today()
            
            if date_range == "today":
                query = query.filter(func.date(Case.uploaded_at) == today)
            elif date_range == "yesterday":
                query = query.filter(func.date(Case.uploaded_at) == today - timedelta(days=1))
            elif date_range == "last_7_days":
                query = query.filter(Case.uploaded_at >= today - timedelta(days=7))
            elif date_range == "last_30_days":
                query = query.filter(Case.uploaded_at >= today - timedelta(days=30))
            elif date_range == "this_month":
                query = query.filter(
                    and_(
                        func.extract('month', Case.uploaded_at) == today.month,
                        func.extract('year', Case.uploaded_at) == today.year
                    )
                )
            elif date_range == "this_year":
                query = query.filter(func.extract('year', Case.uploaded_at) == today.year)

        # Map user-friendly sort field names
        sort_by_mapped = sort_by
        if sort_by == "urgency":
            sort_by_mapped = "priority"  # Map urgency to priority field

        # Get total count before pagination (outer join won't affect count)
        total = query.count()

        # Apply sorting based on field type
        if sort_by_mapped == "days_open":
            # Computed sorting: days between uploaded_at and now
            # Use SQL expression to calculate days
            days_open_expr = func.extract('epoch', func.now() - Case.uploaded_at) / 86400.0
            if sort_order == "desc":
                query = query.order_by(days_open_expr.desc())
            else:
                query = query.order_by(days_open_expr)
        elif sort_by_mapped == "case_type":
            # Sort by request_type from extracted_data JSON field
            # Join with ClinicalExtraction to access extracted_data
            from app.models.extraction import ClinicalExtraction
            
            query = query.outerjoin(
                ClinicalExtraction,
                Case.id == ClinicalExtraction.case_id
            )
            
            # Extract request_type from JSON using PostgreSQL JSON operators
            # PostgreSQL JSON path: extracted_data->'request_metadata'->>'request_type'
            # Use SQLAlchemy JSON operators: -> for JSON object, ->> for text extraction
            extracted_data = ClinicalExtraction.extracted_data
            request_metadata = extracted_data.op("->")("request_metadata")
            request_type = request_metadata.op("->>")("request_type")
            
            # Use COALESCE to handle NULL values, put empty strings last
            request_type_expr = func.coalesce(
                func.nullif(request_type, ''),
                'ZZZ'  # Put null/empty values at the end when sorting ascending
            )
            
            if sort_order == "desc":
                query = query.order_by(request_type_expr.desc())
            else:
                query = query.order_by(request_type_expr)
        elif hasattr(Case, sort_by_mapped):
            # Standard field sorting
            sort_field = getattr(Case, sort_by_mapped)
            if sort_order == "desc":
                query = query.order_by(sort_field.desc())
            else:
                query = query.order_by(sort_field)
        else:
            # Default fallback
            query = query.order_by(Case.uploaded_at.desc())

        # Apply pagination
        cases = query.offset(skip).limit(limit).all()

        return cases, total

    def update_status(
        self, db: Session, case_id: str, status: CaseStatus
    ) -> Optional[Case]:
        """
        Update case status

        Args:
            db: Database session
            case_id: Case ID
            status: New status

        Returns:
            Updated case or None if not found
        """
        case = self.get_by_id(db, case_id)
        if case:
            case.status = status
            return self.update(db, case)
        return None

