"""Dashboard orchestration endpoints."""
import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from app.db.session import get_db
from app.db.dependencies import (
    get_dashboard_snapshot_repository,
    get_facet_repository,
    get_source_link_repository,
    get_extraction_repository,
)
from app.repositories.dashboard_snapshot_repository import DashboardSnapshotRepository
from app.repositories.facet_repository import FacetRepository
from app.repositories.source_link_repository import SourceLinkRepository
from app.repositories.extraction_repository import ExtractionRepository
from app.schemas.dashboard import DashboardResponse, DashboardSnapshotResponse, FacetResultResponse
from app.services.orchestrator_service import build_orchestrator_service
from app.models.dashboard import FacetType
from app.api.endpoints.auth import get_current_user
from app.models.user import User

router = APIRouter()


def _serialize_snapshot(snapshot) -> DashboardResponse:
    facets = {facet.facet_type: facet for facet in snapshot.facets}
    return DashboardResponse(
        snapshot=DashboardSnapshotResponse.from_orm(snapshot),
        facets={
            facet_type: FacetResultResponse.from_orm(facet)
            for facet_type, facet in facets.items()
        },
    )


@router.get("/dashboard/{case_id}", response_model=DashboardResponse)
async def get_dashboard(
    case_id: str,
    db: Session = Depends(get_db),
    snapshot_repository: DashboardSnapshotRepository = Depends(
        get_dashboard_snapshot_repository
    ),
    facet_repository: FacetRepository = Depends(get_facet_repository),
    current_user: User = Depends(get_current_user),
):
    snapshot = snapshot_repository.get_latest_for_case(db, case_id, user_id=current_user.id)
    if not snapshot:
        # Check if case is ready - if so, auto-build the dashboard
        from app.repositories.case_repository import CaseRepository
        from app.db.dependencies import get_case_repository
        from app.models.case import CaseStatus
        
        case_repo = get_case_repository()
        case = case_repo.get_by_id(db, case_id, user_id=current_user.id)
        
        if case and case.status == CaseStatus.READY:
            # Case is ready but dashboard not built yet - build it automatically
            try:
                logger.info(f"Auto-building dashboard for ready case {case_id}")
                orchestrator = build_orchestrator_service()
                snapshot = orchestrator.build_dashboard(db=db, case_id=case_id, user_id=current_user.id, force_reprocess=False)
                logger.info(f"Successfully auto-built dashboard for case {case_id}")
            except Exception as e:
                logger.warning(f"Failed to auto-build dashboard for case {case_id}: {e}", exc_info=True)
                raise HTTPException(status_code=404, detail="Dashboard not found and could not be built")
        else:
            raise HTTPException(status_code=404, detail="Dashboard not found")

    # Ensure facets are loaded
    snapshot.facets = facet_repository.list_for_snapshot(db, snapshot.id)
    return _serialize_snapshot(snapshot)


@router.post("/dashboard/{case_id}/build", response_model=DashboardResponse)
async def build_dashboard(
    case_id: str,
    facet: FacetType | None = Query(default=None),
    force_reprocess: bool = Query(default=False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Verify case belongs to user
    from app.repositories.case_repository import CaseRepository
    from app.db.dependencies import get_case_repository
    case_repo = get_case_repository()
    case = case_repo.get_by_id(db, case_id, user_id=current_user.id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    
    orchestrator = build_orchestrator_service()
    snapshot = orchestrator.build_dashboard(
        db=db, case_id=case_id, user_id=current_user.id, facet=facet, force_reprocess=force_reprocess
    )
    return _serialize_snapshot(snapshot)


@router.post("/dashboard/{case_id}/facet/{facet_type}/rerun", response_model=DashboardResponse)
async def rerun_facet(
    case_id: str,
    facet_type: FacetType,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Verify case belongs to user
    from app.repositories.case_repository import CaseRepository
    from app.db.dependencies import get_case_repository
    case_repo = get_case_repository()
    case = case_repo.get_by_id(db, case_id, user_id=current_user.id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    
    orchestrator = build_orchestrator_service()
    snapshot = orchestrator.build_dashboard(db=db, case_id=case_id, user_id=current_user.id, facet=facet_type, force_reprocess=False)
    return _serialize_snapshot(snapshot)


@router.get("/dashboard/{case_id}/sources/{facet_type}/{item_id}")
async def get_facet_source(
    case_id: str,
    facet_type: FacetType,
    item_id: str,
    db: Session = Depends(get_db),
    source_link_repository: SourceLinkRepository = Depends(get_source_link_repository),
    extraction_repository: ExtractionRepository = Depends(get_extraction_repository),
    current_user: User = Depends(get_current_user),
):
    # Verify case belongs to user
    from app.repositories.case_repository import CaseRepository
    from app.db.dependencies import get_case_repository
    case_repo = get_case_repository()
    case = case_repo.get_by_id(db, case_id, user_id=current_user.id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    
    links = source_link_repository.list_for_case(db, case_id, user_id=current_user.id)
    # Try exact match
    link = next((l for l in links if l.item_id == item_id), None)
    if link:
        return {
            "source": {
                "file_name": link.file_name,
                "file_id": link.file_id,
                "page": link.page_number,
                "snippet": link.snippet,
                "full_text": link.full_text,
            }
        }

    # Fallback: derive from extraction source mapping
    extraction = extraction_repository.get_by_case_id(db, case_id, user_id=current_user.id)
    if not extraction or not extraction.source_mapping:
        raise HTTPException(status_code=404, detail="Source not found")

    mapping = extraction.source_mapping
    file_page_mapping = mapping.get("file_page_mapping", {}) if isinstance(mapping, dict) else {}
    files = mapping.get("files", []) if isinstance(mapping, dict) else []
    first_file = files[0] if files else {}
    file_id = first_file.get("id")
    file_name = first_file.get("file_name")
    page_number = 1
    page_text = ""
    if file_id and isinstance(file_page_mapping, dict):
        page_text = file_page_mapping.get(file_id, {}).get(page_number, "")

    return {
        "source": {
            "file_name": file_name,
            "file_id": file_id,
            "page": page_number,
            "snippet": page_text[:500] if page_text else "",
            "full_text": page_text or "",
        }
    }

