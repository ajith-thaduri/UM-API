"""Database models"""

from app.db.session import Base
from app.models.case import Case, CaseStatus, Priority
from app.models.case_file import CaseFile
from app.models.extraction import ClinicalExtraction
from app.models.user import User
from app.models.decision import Decision, DecisionType
from app.models.note import CaseNote
from app.models.dashboard import (
    DashboardSnapshot,
    FacetResult,
    SourceLink,
    FacetType,
    FacetStatus,
)
from app.models.document_chunk import DocumentChunk, SectionType
from app.models.user_preference import UserPreference
from app.models.usage_metrics import UsageMetrics
from app.models.evidence_click import EvidenceClick
from app.models.conversation import ConversationMessage
from app.models.entity_source import EntitySource
from app.models.upload_session import UploadSession
from app.models.wallet import Wallet
from app.models.transaction import Transaction
from app.models.prompt import Prompt
from app.models.version_history import VersionHistory, VersionEventType
from app.models.token_blacklist import TokenBlacklist

# Page-indexed RAG models
from app.models.normalized_page import NormalizedPage
from app.models.page_vector import PageVector
from app.models.page_temporal_profile import PageTemporalProfile
from app.models.entity import Entity  # New Entity model

__all__ = [
    "Base",
    "Case",
    "CaseStatus",
    "Priority",
    "CaseFile",
    "ClinicalExtraction",
    "User",
    "Decision",
    "DecisionType",
    "CaseNote",
    "DashboardSnapshot",
    "FacetResult",
    "SourceLink",
    "FacetType",
    "FacetStatus",
    "DocumentChunk",
    "SectionType",
    "UserPreference",
    "UsageMetrics",
    "EvidenceClick",
    "ConversationMessage",
    "EntitySource",
    "UploadSession",
    "Wallet",
    "Transaction",
    "TokenBlacklist",
    "Prompt",
    "VersionHistory",
    "VersionEventType",
    # Page-indexed RAG models
    "NormalizedPage",
    "PageVector",
    "PageTemporalProfile",
    "Entity",
]

