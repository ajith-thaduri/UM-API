"""Data access layer"""

from app.repositories.base import BaseRepository
from app.repositories.case_repository import CaseRepository
from app.repositories.case_file_repository import CaseFileRepository
from app.repositories.extraction_repository import ExtractionRepository
from app.repositories.user_repository import UserRepository
from app.repositories.decision_repository import DecisionRepository
from app.repositories.note_repository import NoteRepository
from app.repositories.dashboard_snapshot_repository import DashboardSnapshotRepository
from app.repositories.facet_repository import FacetRepository
from app.repositories.source_link_repository import SourceLinkRepository
from app.repositories.chunk_repository import ChunkRepository
from app.repositories.user_preference_repository import UserPreferenceRepository
from app.repositories.usage_metrics_repository import UsageMetricsRepository
from app.repositories.entity_source_repository import EntitySourceRepository

__all__ = [
    "BaseRepository",
    "CaseRepository",
    "CaseFileRepository",
    "ExtractionRepository",
    "UserRepository",
    "DecisionRepository",
    "NoteRepository",
    "DashboardSnapshotRepository",
    "FacetRepository",
    "SourceLinkRepository",
    "ChunkRepository",
    "UserPreferenceRepository",
    "UsageMetricsRepository",
    "EntitySourceRepository",
]
