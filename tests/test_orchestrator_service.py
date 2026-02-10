from unittest.mock import MagicMock
import pytest
from sqlalchemy.orm import Session

from app.services.orchestrator_service import OrchestratorService
from app.models.dashboard import FacetType


def test_orchestrator_raises_for_missing_case():
    snapshot_repo = MagicMock()
    facet_repo = MagicMock()
    extraction_repo = MagicMock()
    case_repo = MagicMock()
    source_link_service = MagicMock()

    case_repo.get_by_id.return_value = None
    orchestrator = OrchestratorService(
        snapshot_repo, facet_repo, extraction_repo, case_repo, source_link_service
    )

    with pytest.raises(ValueError):
        orchestrator.build_dashboard(
            db=MagicMock(spec=Session), 
            case_id="missing",
            user_id="test-user-id"
        )

def test_build_dashboard_success():
    snapshot_repo = MagicMock()
    facet_repo = MagicMock()
    extraction_repo = MagicMock()
    case_repo = MagicMock()
    source_link_service = MagicMock()
    
    # Mock case
    case = MagicMock()
    case_repo.get_by_id.return_value = case
    
    # Mock extraction
    extraction = MagicMock()
    extraction.extracted_data = {"diagnoses": ["Hypertension"]}
    extraction.summary = "Summary"
    extraction.timeline = []
    extraction.contradictions = []
    extraction.source_mapping = {}
    extraction_repo.get_by_case_id.return_value = extraction
    
    # Mock snapshot version
    snapshot_repo.next_version.return_value = 1
    
    orchestrator = OrchestratorService(
        snapshot_repo, facet_repo, extraction_repo, case_repo, source_link_service
    )
    
    db = MagicMock(spec=Session)
    snapshot = orchestrator.build_dashboard(
        db=db,
        case_id="case-1",
        user_id="user-1"
    )
    
    assert snapshot is not None
    assert snapshot.status == "ready"
    assert snapshot_repo.next_version.called
    assert facet_repo.add.called or db.add.called

