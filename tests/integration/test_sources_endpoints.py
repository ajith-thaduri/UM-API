"""Integration tests for Sources API endpoints"""

import pytest
import uuid
from unittest.mock import patch, MagicMock
from fastapi import status
from app.models.user import User
from app.models.case import Case, CaseStatus, Priority
from app.models.extraction import ClinicalExtraction
from app.models.case_file import CaseFile


def get_auth_headers(client, email="sources@example.com", password="password123"):
    """Helper to register and get auth token."""
    reg_data = {"email": email, "password": password, "name": "Test User"}
    response = client.post("/api/v1/auth/register", json=reg_data)
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_get_contradiction_sources(client, db):
    """Test getting sources for a contradiction"""
    headers = get_auth_headers(client, "contradictionsources@example.com")
    
    user = db.query(User).filter(User.email == "contradictionsources@example.com").first()
    
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
    
    file1 = CaseFile(
        id=str(uuid.uuid4()),
        case_id=case.id,
        user_id=user.id,
        file_name="test1.pdf",
        file_path="/path/to/test1.pdf",
        file_size=1024,
        page_count=5,
        file_order=0
    )
    db.add(file1)
    
    extraction = ClinicalExtraction(
        id=str(uuid.uuid4()),
        case_id=case.id,
        user_id=user.id,
        extracted_data={"diagnoses": ["Test"]},
        contradictions=[
            {
                "id": "contradiction-1",
                "type": "medication",
                "description": "Test contradiction",
                "sources": [
                    {"file": "test1.pdf", "page": 1}
                ]
            }
        ],
        source_mapping={
            "files": [
                {"id": file1.id, "file_name": "test1.pdf"}
            ],
            "file_page_mapping": {
                file1.id: {
                    "1": "Test page text content"
                }
            }
        }
    )
    db.add(extraction)
    db.commit()
    
    response = client.get(f"/api/v1/contradiction-evidence/{case.id}/contradiction-1", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "contradiction" in data
    assert "sources" in data
    assert len(data["sources"]) > 0


@patch("app.services.s3_storage_service.s3_storage_service.get_file_content")
def test_download_file(mock_s3_get_content, client, db, monkeypatch):
    """Test downloading a file"""
    # Patch STORAGE_TYPE to s3
    from app.api.endpoints import sources
    monkeypatch.setattr(sources.settings, "STORAGE_TYPE", "s3")
    
    headers = get_auth_headers(client, "downloadfile@example.com")
    
    user = db.query(User).filter(User.email == "downloadfile@example.com").first()
    
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
    
    file = CaseFile(
        id=str(uuid.uuid4()),
        case_id=case.id,
        user_id=user.id,
        file_name="test.pdf",
        file_path="/path/to/test.pdf",
        file_size=1024,
        page_count=5,
        file_order=0
    )
    db.add(file)
    db.commit()
    
    # Mock S3 file content for proxy mode
    mock_s3_get_content.return_value = b"fake pdf content"
    
    # Use use_proxy=true to force backend streaming (returns PDF instead of JSON URL)
    response = client.get(f"/api/v1/cases/{case.id}/files/{file.id}/pdf?use_proxy=true", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    assert response.headers["content-type"] == "application/pdf"


@patch("app.services.pdf_service.pdf_service.extract_text_from_pdf")
def test_preview_file(mock_extract_text, client, db):
    """Test previewing a file page"""
    headers = get_auth_headers(client, "previewfile@example.com")
    
    user = db.query(User).filter(User.email == "previewfile@example.com").first()
    
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
    
    file = CaseFile(
        id=str(uuid.uuid4()),
        case_id=case.id,
        user_id=user.id,
        file_name="test.pdf",
        file_path="/path/to/test.pdf",
        file_size=1024,
        page_count=5,
        file_order=0
    )
    db.add(file)
    db.commit()
    
    # Mock PDF text extraction
    mock_extract_text.return_value = {
        "pages": [{"page_number": 1, "text": "Page 1 content"}],
        "page_count": 5
    }
    
    # Correct route: /api/v1/cases/{case_id}/files/{file_id}/page/{page}
    response = client.get(f"/api/v1/cases/{case.id}/files/{file.id}/page/1", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "text" in data or "content" in data
