"""Integration tests for Annotations API endpoints"""

import pytest
import uuid
from datetime import datetime, timezone
from fastapi import status
from app.models.user import User
from app.models.case import Case, CaseStatus, Priority
from app.models.extraction import ClinicalExtraction
from app.models.note import CaseNote


def get_auth_headers(client, email="annotations@example.com", password="password123"):
    """Helper to register and get auth token."""
    reg_data = {"email": email, "password": password, "name": "Test User"}
    response = client.post("/api/v1/auth/register", json=reg_data)
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_update_summary_section(client, db):
    """Test updating a summary section"""
    headers = get_auth_headers(client, "updatesummary@example.com")
    
    user = db.query(User).filter(User.email == "updatesummary@example.com").first()
    
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
    
    extraction = ClinicalExtraction(
        id=str(uuid.uuid4()),
        case_id=case.id,
        user_id=user.id,
        extracted_data={"diagnoses": ["Test"]},
        summary="Original summary"
    )
    db.add(extraction)
    db.commit()
    
    update_data = {
        "section_name": "summary",
        "content": "Updated summary content",
        "edited_by": "Test Editor"
    }
    
    response = client.put(f"/api/v1/extractions/{case.id}/summary/section", json=update_data, headers=headers)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["section_name"] == "summary"
    
    # Verify edited_sections was updated
    db.refresh(extraction)
    assert extraction.edited_sections is not None
    assert "summary" in extraction.edited_sections


def test_get_edited_sections(client, db):
    """Test getting edited sections"""
    headers = get_auth_headers(client, "getedited@example.com")
    
    user = db.query(User).filter(User.email == "getedited@example.com").first()
    
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
    
    extraction = ClinicalExtraction(
        id=str(uuid.uuid4()),
        case_id=case.id,
        user_id=user.id,
        extracted_data={"diagnoses": ["Test"]},
        edited_sections={"summary": {"content": "Edited content", "edited_by": "Editor"}}
    )
    db.add(extraction)
    db.commit()
    
    response = client.get(f"/api/v1/extractions/{case.id}/summary/sections", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "edited_sections" in data
    assert "summary" in data["edited_sections"]


def test_get_case_notes(client, db):
    """Test getting case notes"""
    headers = get_auth_headers(client, "getnotes@example.com")
    
    user = db.query(User).filter(User.email == "getnotes@example.com").first()
    
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
    
    note1 = CaseNote(
        id=str(uuid.uuid4()),
        case_id=case.id,
        user_id=user.id,
        author="Author 1",
        text="Note 1",
        created_at=datetime.now(timezone.utc)
    )
    note2 = CaseNote(
        id=str(uuid.uuid4()),
        case_id=case.id,
        user_id=user.id,
        author="Author 2",
        text="Note 2",
        created_at=datetime.now(timezone.utc)
    )
    db.add(note1)
    db.add(note2)
    db.commit()
    
    response = client.get(f"/api/v1/cases/{case.id}/notes", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert len(data) == 2


def test_create_case_note(client, db):
    """Test creating a case note"""
    headers = get_auth_headers(client, "createnote@example.com")
    
    user = db.query(User).filter(User.email == "createnote@example.com").first()
    
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
    
    note_data = {
        "text": "This is a test note",
        "author": "Test Author"
    }
    
    response = client.post(f"/api/v1/cases/{case.id}/notes", json=note_data, headers=headers)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["text"] == "This is a test note"
    assert data["case_id"] == case.id


def test_delete_case_note(client, db):
    """Test deleting a case note"""
    headers = get_auth_headers(client, "deletenote@example.com")
    
    user = db.query(User).filter(User.email == "deletenote@example.com").first()
    
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
    
    note = CaseNote(
        id=str(uuid.uuid4()),
        case_id=case.id,
        user_id=user.id,
        author="Test Author",
        text="Test note",
        created_at=datetime.now(timezone.utc)
    )
    db.add(note)
    db.commit()
    
    response = client.delete(f"/api/v1/cases/{case.id}/notes/{note.id}", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    
    # Verify deleted
    found_note = db.query(CaseNote).filter(CaseNote.id == note.id).first()
    assert found_note is None


def test_delete_case_note_not_found(client, db):
    """Test deleting non-existent note"""
    headers = get_auth_headers(client, "deletenotefound@example.com")
    
    user = db.query(User).filter(User.email == "deletenotefound@example.com").first()
    
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
    
    response = client.delete(f"/api/v1/cases/{case.id}/notes/non-existent-id", headers=headers)
    assert response.status_code == status.HTTP_404_NOT_FOUND
