"""Integration tests for Decisions API endpoints"""

import pytest
import uuid
from datetime import datetime, timezone
from fastapi import status
from app.models.user import User
from app.models.case import Case, CaseStatus, Priority
from app.models.decision import Decision, DecisionType


def get_auth_headers(client, email="decisions@example.com", password="password123"):
    """Helper to register and get auth token."""
    reg_data = {"email": email, "password": password, "name": "Test User"}
    response = client.post("/api/v1/auth/register", json=reg_data)
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_create_decision(client, db):
    """Test creating a decision"""
    headers = get_auth_headers(client, "createdecision@example.com")
    
    user = db.query(User).filter(User.email == "createdecision@example.com").first()
    
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
    db.commit()
    
    decision_data = {
        "decision_type": "approved",
        "sub_status": "standard",
        "notes": "Test decision notes",
        "decided_by": "Test Reviewer"
    }
    
    response = client.post(f"/api/v1/cases/{case.id}/decision", json=decision_data, headers=headers)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["decision_type"] == "approved"
    assert data["case_id"] == case.id
    
    # Verify case is marked as reviewed
    db.refresh(case)
    assert case.is_reviewed is True


def test_create_decision_duplicate(client, db):
    """Test creating duplicate decision"""
    headers = get_auth_headers(client, "duplicatedecision@example.com")
    
    user = db.query(User).filter(User.email == "duplicatedecision@example.com").first()
    
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
    
    decision = Decision(
        id=str(uuid.uuid4()),
        case_id=case.id,
        user_id=user.id,
        decision_type=DecisionType.APPROVED,
        decided_by="Reviewer 1",
        decided_at=datetime.now(timezone.utc)
    )
    db.add(decision)
    db.commit()
    
    decision_data = {
        "decision_type": "denied",
        "decided_by": "Reviewer 2"
    }
    
    response = client.post(f"/api/v1/cases/{case.id}/decision", json=decision_data, headers=headers)
    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_get_decision(client, db):
    """Test getting a decision"""
    headers = get_auth_headers(client, "getdecision@example.com")
    
    user = db.query(User).filter(User.email == "getdecision@example.com").first()
    
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
    
    decision = Decision(
        id=str(uuid.uuid4()),
        case_id=case.id,
        user_id=user.id,
        decision_type=DecisionType.APPROVED,
        decided_by="Test Reviewer",
        decided_at=datetime.now(timezone.utc)
    )
    db.add(decision)
    db.commit()
    
    response = client.get(f"/api/v1/cases/{case.id}/decision", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["decision_type"] == "approved"
    assert data["case_id"] == case.id


def test_get_decision_not_found(client, db):
    """Test getting decision for case without decision"""
    headers = get_auth_headers(client, "nodecision@example.com")
    
    user = db.query(User).filter(User.email == "nodecision@example.com").first()
    
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
    db.commit()
    
    response = client.get(f"/api/v1/cases/{case.id}/decision", headers=headers)
    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_update_decision(client, db):
    """Test updating a decision"""
    headers = get_auth_headers(client, "updatedecision@example.com")
    
    user = db.query(User).filter(User.email == "updatedecision@example.com").first()
    
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
    
    decision = Decision(
        id=str(uuid.uuid4()),
        case_id=case.id,
        user_id=user.id,
        decision_type=DecisionType.PENDING,
        decided_by="Test Reviewer",
        decided_at=datetime.now(timezone.utc)
    )
    db.add(decision)
    db.commit()
    
    update_data = {
        "decision_type": "approved",
        "notes": "Updated notes"
    }
    
    response = client.put(f"/api/v1/cases/{case.id}/decision", json=update_data, headers=headers)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["decision_type"] == "approved"
    assert data["notes"] == "Updated notes"


def test_mark_case_reviewed(client, db):
    """Test marking case as reviewed"""
    headers = get_auth_headers(client, "markreviewed@example.com")
    
    user = db.query(User).filter(User.email == "markreviewed@example.com").first()
    
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
    db.commit()
    
    response = client.post(f"/api/v1/cases/{case.id}/mark-reviewed?reviewed_by=Test+Reviewer", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    
    # Verify case is marked as reviewed
    db.refresh(case)
    assert case.is_reviewed is True
    assert case.reviewed_by == "Test Reviewer"
