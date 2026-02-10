"""Repository dependency injection functions"""

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.repositories.case_repository import CaseRepository
from app.repositories.case_file_repository import CaseFileRepository
from app.repositories.extraction_repository import ExtractionRepository
from app.repositories.user_repository import UserRepository
from app.repositories.decision_repository import DecisionRepository
from app.repositories.note_repository import NoteRepository
from app.repositories.dashboard_snapshot_repository import DashboardSnapshotRepository
from app.repositories.facet_repository import FacetRepository
from app.repositories.source_link_repository import SourceLinkRepository
from app.repositories.user_preference_repository import UserPreferenceRepository
from app.repositories.usage_metrics_repository import UsageMetricsRepository


def get_case_repository(db: Session = Depends(get_db)) -> CaseRepository:
    """Get CaseRepository instance"""
    return CaseRepository()


def get_case_file_repository(
    db: Session = Depends(get_db),
) -> CaseFileRepository:
    """Get CaseFileRepository instance"""
    return CaseFileRepository()


def get_extraction_repository(
    db: Session = Depends(get_db),
) -> ExtractionRepository:
    """Get ExtractionRepository instance"""
    return ExtractionRepository()


def get_user_repository(db: Session = Depends(get_db)) -> UserRepository:
    """Get UserRepository instance"""
    return UserRepository()


def get_decision_repository(
    db: Session = Depends(get_db),
) -> DecisionRepository:
    """Get DecisionRepository instance"""
    return DecisionRepository()


def get_note_repository(db: Session = Depends(get_db)) -> NoteRepository:
    """Get NoteRepository instance"""
    return NoteRepository()


def get_dashboard_snapshot_repository(
    db: Session = Depends(get_db),
) -> DashboardSnapshotRepository:
    """Get DashboardSnapshotRepository instance"""
    return DashboardSnapshotRepository()


def get_facet_repository(db: Session = Depends(get_db)) -> FacetRepository:
    """Get FacetRepository instance"""
    return FacetRepository()


def get_source_link_repository(
    db: Session = Depends(get_db),
) -> SourceLinkRepository:
    """Get SourceLinkRepository instance"""
    return SourceLinkRepository()


def get_user_preference_repository(
    db: Session = Depends(get_db),
) -> UserPreferenceRepository:
    """Get UserPreferenceRepository instance"""
    return UserPreferenceRepository()


def get_usage_metrics_repository(
    db: Session = Depends(get_db),
) -> UsageMetricsRepository:
    """Get UsageMetricsRepository instance"""
    return UsageMetricsRepository()

