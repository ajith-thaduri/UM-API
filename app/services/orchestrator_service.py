"""Main orchestrator that coordinates facet agents and builds dashboard snapshots."""
import uuid
from typing import Dict, Optional
from sqlalchemy.orm import Session
from datetime import datetime
import logging

from app.models.dashboard import DashboardSnapshot, FacetResult, FacetStatus, FacetType
from app.models.extraction import ClinicalExtraction
from app.repositories.dashboard_snapshot_repository import DashboardSnapshotRepository
from app.repositories.facet_repository import FacetRepository
from app.repositories.extraction_repository import ExtractionRepository
from app.repositories.case_repository import CaseRepository
from app.services.case_processor import CaseProcessor
from app.services.timeline_service import timeline_service
from app.services.contradiction_service import contradiction_service
from app.services.red_flags_service import red_flags_service
from app.services.source_link_service import SourceLinkService, build_source_link_service

logger = logging.getLogger(__name__)


class OrchestratorService:
    """Coordinates agents and snapshots."""

    def __init__(
        self,
        snapshot_repository: DashboardSnapshotRepository,
        facet_repository: FacetRepository,
        extraction_repository: ExtractionRepository,
        case_repository: CaseRepository,
        source_link_service: SourceLinkService,
    ):
        self.snapshot_repository = snapshot_repository
        self.facet_repository = facet_repository
        self.extraction_repository = extraction_repository
        self.case_repository = case_repository
        self.case_processor = CaseProcessor()
        self.source_link_service = source_link_service

    def build_dashboard(
        self,
        db: Session,
        case_id: str,
        user_id: str,
        facet: Optional[FacetType] = None,
        force_reprocess: bool = False,
    ) -> DashboardSnapshot:
        """Build dashboard snapshot. Optionally rebuild a single facet."""
        case = self.case_repository.get_by_id(db, case_id, user_id=user_id)
        if not case:
            raise ValueError("Case not found")

        extraction = self._get_or_process_extraction(db, case_id, force_reprocess)

        version = self.snapshot_repository.next_version(db, case_id, user_id)
        snapshot = DashboardSnapshot(
            id=str(uuid.uuid4()),
            case_id=case_id,
            user_id=user_id,
            version=version,
            status=FacetStatus.PENDING,
            created_at=datetime.utcnow(),
        )
        db.add(snapshot)
        db.commit()
        db.refresh(snapshot)

        try:
            facets_to_build = (
                [facet]
                if facet
                else [
                    FacetType.CASE_OVERVIEW,
                    FacetType.SUMMARY,
                    FacetType.CLINICAL,
                    FacetType.TIMELINE,
                    FacetType.RED_FLAGS,
                    FacetType.CONTRADICTIONS,
                ]
            )
            built_facets = {}
            for facet_type in facets_to_build:
                built = self._build_facet(db, snapshot, extraction, facet_type, user_id)
                built_facets[facet_type] = built
                self.source_link_service.sync_links_for_facet(
                    db, built, extraction.source_mapping
                )

            snapshot.status = FacetStatus.READY
            snapshot.updated_at = datetime.utcnow()
            db.commit()
            db.refresh(snapshot)
            snapshot.facets = list(built_facets.values())
            return snapshot
        except Exception as exc:
            logger.exception("Failed to build dashboard")
            snapshot.status = FacetStatus.FAILED
            snapshot.error = str(exc)
            snapshot.updated_at = datetime.utcnow()
            db.commit()
            db.refresh(snapshot)
            raise

    def _get_or_process_extraction(
        self, db: Session, case_id: str, force_reprocess: bool
    ) -> ClinicalExtraction:
        extraction = self.extraction_repository.get_by_case_id(db, case_id)
        if extraction and not force_reprocess:
            return extraction

        result = self.case_processor.process_case(case_id)
        if not result.get("success"):
            raise ValueError(result.get("error") or "Processing failed")

        extraction = self.extraction_repository.get_by_case_id(db, case_id)
        if not extraction:
            raise ValueError("Extraction missing after processing")
        return extraction

    def _build_facet(
        self,
        db: Session,
        snapshot: DashboardSnapshot,
        extraction: ClinicalExtraction,
        facet_type: FacetType,
        user_id: str,
    ) -> FacetResult:
        content: Dict = {}
        if facet_type == FacetType.CASE_OVERVIEW:
            # Extract request metadata from extracted_data
            request_metadata = {}
            if extraction.extracted_data and isinstance(extraction.extracted_data, dict):
                request_metadata = extraction.extracted_data.get('request_metadata', {})
            
            # Extract diagnoses from clinical data
            diagnoses = []
            if extraction.extracted_data and isinstance(extraction.extracted_data, dict):
                extracted_diagnoses = extraction.extracted_data.get('diagnoses', [])
                for dx in extracted_diagnoses[:5]:  # First 5 diagnoses
                    if isinstance(dx, str):
                        diagnoses.append(dx)
                    elif isinstance(dx, dict):
                        name = dx.get('name', '')
                        if name:
                            diagnoses.append(name)
            
            content = {
                "request_type": request_metadata.get('request_type', 'Not specified'),
                "requested_service": request_metadata.get('requested_service', 'Not specified'),
                "diagnosis": ", ".join(diagnoses) if diagnoses else "Not explicitly documented",
                "request_date": request_metadata.get('request_date', 'Not specified'),
                "urgency": request_metadata.get('urgency', 'Routine')
            }
        elif facet_type == FacetType.SUMMARY:
            content = {
                "text": extraction.summary,
                "edited_sections": extraction.edited_sections,
                "executive_summary": getattr(extraction, "executive_summary", None),
            }
        elif facet_type == FacetType.CLINICAL:
            content = extraction.extracted_data or {}
        elif facet_type == FacetType.TIMELINE:
            content = extraction.timeline or []
            if not content and extraction.extracted_data:
                timeline_result = timeline_service.build_timeline(extraction.extracted_data, "", db=db, case_id=snapshot.case_id, user_id=user_id)
                # timeline_result is now a Dict with 'summary' and 'detailed' keys
                content = timeline_result.get("detailed", [])
                # Also save summary timeline if not already present
                if not extraction.timeline_summary:
                    extraction.timeline_summary = timeline_result.get("summary", [])
                    db.commit()
        elif facet_type == FacetType.CONTRADICTIONS:
            content = extraction.contradictions or []
            if not content and extraction.extracted_data:
                content = contradiction_service.detect_contradictions(
                    extraction.extracted_data, extraction.timeline or []
                )
        elif facet_type == FacetType.RED_FLAGS:
            # Run async detect in sync context
            import asyncio
            try:
                # Try to get existing event loop
                try:
                    loop = asyncio.get_running_loop()
                    # If we're in an async context, we can't use asyncio.run
                    # Create a new event loop in a thread
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(
                            lambda: asyncio.run(red_flags_service.detect(
                                extraction.extracted_data or {},
                                extraction.timeline or [],
                                db=db,
                                user_id=user_id,
                                case_id=snapshot.case_id
                            ))
                        )
                        content = future.result()
                except RuntimeError:
                    # No running loop, can use asyncio.run
                    content = asyncio.run(red_flags_service.detect(
                        extraction.extracted_data or {},
                        extraction.timeline or [],
                        db=db,
                        user_id=user_id,
                        case_id=snapshot.case_id
                    ))
            except Exception as e:
                logger.error(f"Error running red flags detection: {e}", exc_info=True)
                content = []

        sources = extraction.source_mapping or {}

        facet = FacetResult(
            id=str(uuid.uuid4()),
            snapshot_id=snapshot.id,
            case_id=snapshot.case_id,
            user_id=user_id,
            facet_type=facet_type,
            status=FacetStatus.READY,
            content=content,
            sources=sources,
            created_at=datetime.utcnow(),
        )

        db.add(facet)
        db.commit()
        db.refresh(facet)
        return facet


def build_orchestrator_service() -> OrchestratorService:
    return OrchestratorService(
        DashboardSnapshotRepository(),
        FacetRepository(),
        ExtractionRepository(),
        CaseRepository(),
        build_source_link_service(),
    )

