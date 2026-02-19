"""Integration tests for Dashboard API endpoints"""

import pytest
import uuid
from datetime import datetime
from unittest.mock import patch, MagicMock
from fastapi import status
from app.models.user import User
from app.models.case import Case, CaseStatus, Priority
from app.models.dashboard import DashboardSnapshot, FacetResult, FacetType, FacetStatus


def get_auth_headers(client, email="dashboard@example.com", password="password123"):
    """Helper to register and get auth token."""
    reg_data = {"email": email, "password": password, "name": "Test User"}
    response = client.post("/api/v1/auth/register", json=reg_data)
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_get_dashboard(client, db):
    """Test getting dashboard for a case"""
    headers = get_auth_headers(client, "getdashboard@example.com")
    
    user = db.query(User).filter(User.email == "getdashboard@example.com").first()
    
    case = Case(
        id=str(uuid.uuid4()),
        patient_id="PAT-001",
        patient_name="Test Patient",
        case_number=f"CASE-{uuid.uuid4().hex[:6]}",
        status=CaseStatus.READY,
        priority=Priority.NORMAL,
        user_id=user.id
    )
    db.add(case)
    db.flush()
    
    snapshot = DashboardSnapshot(
        id=str(uuid.uuid4()),
        case_id=case.id,
        user_id=user.id,
        version=1,
        status=FacetStatus.READY,
        created_at=datetime.utcnow()
    )
    db.add(snapshot)
    db.flush()
    
    facet = FacetResult(
        id=str(uuid.uuid4()),
        snapshot_id=snapshot.id,
        case_id=case.id,
        user_id=user.id,
        facet_type=FacetType.SUMMARY,
        status=FacetStatus.READY,
        content={"summary": "Test summary"},
        created_at=datetime.utcnow()
    )
    db.add(facet)
    db.commit()
    
    response = client.get(f"/api/v1/dashboard/{case.id}", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "snapshot" in data
    assert "facets" in data


def test_get_dashboard_not_found(client, db):
    """Test getting dashboard for case without snapshot"""
    headers = get_auth_headers(client, "nodashboard@example.com")
    
    user = db.query(User).filter(User.email == "nodashboard@example.com").first()
    
    case = Case(
        id=str(uuid.uuid4()),
        patient_id="PAT-001",
        patient_name="Test Patient",
        case_number=f"CASE-{uuid.uuid4().hex[:6]}",
        status=CaseStatus.UPLOADED,  # Not ready, so won't auto-build
        priority=Priority.NORMAL,
        user_id=user.id
    )
    db.add(case)
    db.commit()
    
    response = client.get(f"/api/v1/dashboard/{case.id}", headers=headers)
    assert response.status_code == status.HTTP_404_NOT_FOUND


@patch("app.api.endpoints.dashboard.build_orchestrator_service")
def test_build_dashboard(mock_build_service, client, db):
    """Test building dashboard"""
    headers = get_auth_headers(client, "builddashboard@example.com")
    
    user = db.query(User).filter(User.email == "builddashboard@example.com").first()
    
    case = Case(
        id=str(uuid.uuid4()),
        patient_id="PAT-001",
        patient_name="Test Patient",
        case_number=f"CASE-{uuid.uuid4().hex[:6]}",
        status=CaseStatus.READY,
        priority=Priority.NORMAL,
        user_id=user.id
    )
    db.add(case)
    db.flush()
    
    # Create a real snapshot in DB
    snapshot = DashboardSnapshot(
        id=str(uuid.uuid4()),
        case_id=case.id,
        user_id=user.id,
        version=1,
        status=FacetStatus.READY,
        created_at=datetime.utcnow()
    )
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    
    # Mock orchestrator
    mock_orchestrator = MagicMock()
    mock_orchestrator.build_dashboard.return_value = snapshot
    mock_build_service.return_value = mock_orchestrator
    
    response = client.post(f"/api/v1/dashboard/{case.id}/build", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "snapshot" in data


@patch("app.api.endpoints.dashboard.build_orchestrator_service")
def test_rerun_facet(mock_build_service, client, db):
    """Test rerunning a specific facet"""
    headers = get_auth_headers(client, "rerunfacet@example.com")
    
    user = db.query(User).filter(User.email == "rerunfacet@example.com").first()
    
    case = Case(
        id=str(uuid.uuid4()),
        patient_id="PAT-001",
        patient_name="Test Patient",
        case_number=f"CASE-{uuid.uuid4().hex[:6]}",
        status=CaseStatus.READY,
        priority=Priority.NORMAL,
        user_id=user.id
    )
    db.add(case)
    db.flush()
    
    # Create a real snapshot in DB
    snapshot = DashboardSnapshot(
        id=str(uuid.uuid4()),
        case_id=case.id,
        user_id=user.id,
        version=1,
        status=FacetStatus.READY,
        created_at=datetime.utcnow()
    )
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    
    # Mock orchestrator
    mock_orchestrator = MagicMock()
    mock_orchestrator.build_dashboard.return_value = snapshot
    mock_build_service.return_value = mock_orchestrator
    
    response = client.post(f"/api/v1/dashboard/{case.id}/facet/{FacetType.SUMMARY.value}/rerun", headers=headers)
    assert response.status_code == status.HTTP_200_OK


def test_get_facet_source(client, db):
    """Test getting source for a facet item"""
    headers = get_auth_headers(client, "facetsource@example.com")
    
    user = db.query(User).filter(User.email == "facetsource@example.com").first()
    
    case = Case(
        id=str(uuid.uuid4()),
        patient_id="PAT-001",
        patient_name="Test Patient",
        case_number=f"CASE-{uuid.uuid4().hex[:6]}",
        status=CaseStatus.READY,
        priority=Priority.NORMAL,
        user_id=user.id
    )
    db.add(case)
    db.flush()
    
    snapshot = DashboardSnapshot(
        id=str(uuid.uuid4()),
        case_id=case.id,
        user_id=user.id,
        version=1,
        status=FacetStatus.READY,
        created_at=datetime.utcnow()
    )
    db.add(snapshot)
    db.flush()
    
    facet = FacetResult(
        id=str(uuid.uuid4()),
        snapshot_id=snapshot.id,
        case_id=case.id,
        user_id=user.id,
        facet_type=FacetType.SUMMARY,
        status=FacetStatus.READY,
        created_at=datetime.utcnow()
    )
    db.add(facet)
    db.flush()
    
    from app.models.dashboard import SourceLink
    source_link = SourceLink(
        id=str(uuid.uuid4()),
        case_id=case.id,
        user_id=user.id,
        facet_id=facet.id,
        item_id="item-1",
        file_id="file-1",
        file_name="test.pdf",
        page_number=1,
        snippet="Test snippet",
        full_text="Test full text",
        created_at=datetime.utcnow()
    )
    db.add(source_link)
    db.commit()
    
    response = client.get(f"/api/v1/dashboard/{case.id}/sources/{FacetType.SUMMARY.value}/item-1", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "source" in data
