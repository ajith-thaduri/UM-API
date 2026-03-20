"""Integration tests for Cases API endpoints"""

import pytest
import uuid
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi import status
from fastapi.testclient import TestClient
from app.models.user import User
from app.models.case import Case, CaseStatus, Priority
from app.models.case_file import CaseFile


def get_auth_headers(client, email="cases@example.com", password="password123"):
    """Helper to register and get auth token."""
    reg_data = {"email": email, "password": password, "name": "Test User"}
    response = client.post("/api/v1/auth/register", json=reg_data)
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_get_cases(client, db):
    """Test getting list of cases"""
    headers = get_auth_headers(client, "getcases@example.com")
    
    user = db.query(User).filter(User.email == "getcases@example.com").first()
    
    # Create test cases
    case1 = Case(
        id=str(uuid.uuid4()),
        patient_id="PAT-001",
        patient_name="Patient 1",
        case_number=f"CASE-{uuid.uuid4().hex[:6]}",
        status=CaseStatus.READY,
        priority=Priority.NORMAL,
        user_id=user.id
    )
    case2 = Case(
        id=str(uuid.uuid4()),
        patient_id="PAT-002",
        patient_name="Patient 2",
        case_number=f"CASE-{uuid.uuid4().hex[:6]}",
        status=CaseStatus.UPLOADED,
        priority=Priority.HIGH,
        user_id=user.id
    )
    db.add(case1)
    db.add(case2)
    db.commit()
    
    response = client.get("/api/v1/cases", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "items" in data
    assert "total" in data
    assert data["total"] >= 2


def test_get_cases_with_filters(client, db):
    """Test getting cases with filters"""
    headers = get_auth_headers(client, "filtercases@example.com")
    
    user = db.query(User).filter(User.email == "filtercases@example.com").first()
    
    case = Case(
        id=str(uuid.uuid4()),
        patient_id="PAT-001",
        patient_name="Patient 1",
        case_number=f"CASE-{uuid.uuid4().hex[:6]}",
        status=CaseStatus.READY,
        priority=Priority.HIGH,
        user_id=user.id
    )
    db.add(case)
    db.commit()
    
    # Filter by status
    response = client.get("/api/v1/cases?status=ready", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert all(item["status"] == "ready" for item in data["items"])
    
    # Filter by priority
    response = client.get("/api/v1/cases?priority=high", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert all(item["priority"] == "high" for item in data["items"])


def test_get_cases_pagination(client, db):
    """Test pagination for cases"""
    headers = get_auth_headers(client, "paginatecases@example.com")
    
    user = db.query(User).filter(User.email == "paginatecases@example.com").first()
    
    # Create multiple cases
    for i in range(5):
        case = Case(
            id=str(uuid.uuid4()),
            patient_id=f"PAT-{i:03d}",
            patient_name=f"Patient {i}",
            case_number=f"CASE-{uuid.uuid4().hex[:6]}",
            status=CaseStatus.READY,
            priority=Priority.NORMAL,
            user_id=user.id
        )
        db.add(case)
    db.commit()
    
    # Get first page
    response = client.get("/api/v1/cases?page=1&page_size=2", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert len(data["items"]) <= 2
    assert data["page"] == 1


def test_get_case(client, db):
    """Test getting a specific case"""
    headers = get_auth_headers(client, "getcase@example.com")
    
    user = db.query(User).filter(User.email == "getcase@example.com").first()
    
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
    
    response = client.get(f"/api/v1/cases/{case.id}", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["id"] == case.id
    assert data["patient_name"] == "Test Patient"


def test_get_case_not_found(client, db):
    """Test getting non-existent case"""
    headers = get_auth_headers(client, "nocase@example.com")
    
    response = client.get("/api/v1/cases/non-existent-id", headers=headers)
    assert response.status_code == status.HTTP_404_NOT_FOUND


@patch("app.services.storage_service.storage_service.save_case_files")
@patch("app.services.pdf_analyzer_service.pdf_analyzer_service.analyze_for_upload")
@patch("app.services.pdf_service.pdf_service.count_pages")
@patch("app.services.case_processor.case_processor.process_case")
def test_upload_case(mock_process, mock_count_pages, mock_analyze, mock_save_files, client, db):
    """Test uploading a case with files"""
    headers = get_auth_headers(client, "uploadcase@example.com")
    
    # Mock file operations
    mock_save_files.return_value = [
        ("/path/to/file1.pdf", 1024, "file1.pdf"),
        ("/path/to/file2.pdf", 2048, "file2.pdf")
    ]
    
    from app.services.pdf_analyzer_service import AnalysisResult, FileAnalysis, PatientInfo
    mock_analyze.return_value = AnalysisResult(
        patient_info=PatientInfo(name="John Doe", dob=None, mrn=None),
        files=[
            FileAnalysis(file_name="file1.pdf", file_path="/path/to/file1.pdf", page_count=5, file_size=1024, extraction_preview="preview", detected_type="medical_record", confidence=0.9),
            FileAnalysis(file_name="file2.pdf", file_path="/path/to/file2.pdf", page_count=10, file_size=2048, extraction_preview="preview", detected_type="social_work", confidence=0.9)
        ],
        total_pages=15,
        extraction_confidence=0.9,
        raw_text_preview="Test preview"
    )
    
    mock_count_pages.return_value = 5
    
    # Create mock file objects
    files = [
        ("files", ("test1.pdf", b"fake pdf content", "application/pdf")),
        ("files", ("test2.pdf", b"fake pdf content", "application/pdf"))
    ]
    
    data = {
        "patient_id": "PAT-001",
        "patient_name": "John Doe",
        "case_number": f"CASE-{uuid.uuid4().hex[:6]}",
        "priority": "normal"
    }
    
    response = client.post("/api/v1/cases/upload", headers=headers, files=files, data=data)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "case_id" in data
    assert data["status"] == "uploaded"


def test_upload_case_duplicate_case_number(client, db):
    """Test uploading case with duplicate case number"""
    headers = get_auth_headers(client, "duplicatecase@example.com")
    
    user = db.query(User).filter(User.email == "duplicatecase@example.com").first()
    
    case_number = f"CASE-{uuid.uuid4().hex[:6]}"
    case = Case(
        id=str(uuid.uuid4()),
        patient_id="PAT-001",
        patient_name="Patient 1",
        case_number=case_number,
        status=CaseStatus.READY,
        priority=Priority.NORMAL,
        user_id=user.id
    )
    db.add(case)
    db.commit()
    
    files = [("files", ("test.pdf", b"fake pdf content", "application/pdf"))]
    data = {
        "patient_id": "PAT-002",
        "patient_name": "Patient 2",
        "case_number": case_number,
        "priority": "normal"
    }
    
    response = client.post("/api/v1/cases/upload", headers=headers, files=files, data=data)
    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_get_case_files(client, db):
    """Test getting files for a case"""
    headers = get_auth_headers(client, "getfiles@example.com")
    
    user = db.query(User).filter(User.email == "getfiles@example.com").first()
    
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
        file_name="file1.pdf",
        file_path="/path/to/file1.pdf",
        file_size=1024,
        page_count=5,
        file_order=0
    )
    file2 = CaseFile(
        id=str(uuid.uuid4()),
        case_id=case.id,
        user_id=user.id,
        file_name="file2.pdf",
        file_path="/path/to/file2.pdf",
        file_size=2048,
        page_count=10,
        file_order=1
    )
    db.add(file1)
    db.add(file2)
    db.commit()
    
    response = client.get(f"/api/v1/cases/{case.id}/files", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["case_id"] == case.id
    assert len(data["files"]) == 2


@patch("app.services.pgvector_service.pgvector_service.delete_case_chunks")
@patch("app.services.storage_service.storage_service.get_case_directory")
def test_delete_case(mock_get_dir, mock_delete_chunks, client, db):
    """Test deleting a case"""
    headers = get_auth_headers(client, "deletecase@example.com")
    
    user = db.query(User).filter(User.email == "deletecase@example.com").first()
    
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
    
    # Mock vector deletion
    mock_delete_chunks.return_value = 10
    
    response = client.delete(f"/api/v1/cases/{case.id}", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    
    # Verify case is deleted
    found_case = db.query(Case).filter(Case.id == case.id).first()
    assert found_case is None


@patch("app.services.case_processor.case_processor.process_case")
def test_generate_summary(mock_process, client, db):
    """Test triggering summary generation"""
    headers = get_auth_headers(client, "summarycase@example.com")
    
    user = db.query(User).filter(User.email == "summarycase@example.com").first()
    
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
    
    mock_process.return_value = AsyncMock()
    
    response = client.post(f"/api/v1/cases/{case.id}/generate-summary", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "message" in data
    assert data["case_id"] == case.id


@patch("app.services.case_processor.case_processor.process_case")
def test_retry_processing(mock_process, client, db):
    """Test retrying case processing"""
    headers = get_auth_headers(client, "retrycase@example.com")
    
    user = db.query(User).filter(User.email == "retrycase@example.com").first()
    
    case = Case(
        id=str(uuid.uuid4()),
        patient_id="PAT-001",
        patient_name="Test Patient",
        case_number=f"CASE-{uuid.uuid4().hex[:6]}",
        status=CaseStatus.FAILED,
        priority=Priority.NORMAL,
        user_id=user.id
    )
    db.add(case)
    db.commit()
    
    mock_process.return_value = AsyncMock()
    
    response = client.post(f"/api/v1/cases/{case.id}/retry", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "message" in data
    
    # Verify status reset
    db.refresh(case)
    assert case.status == CaseStatus.UPLOADED


def test_get_case_status(client, db):
    """Test getting case status"""
    headers = get_auth_headers(client, "statuscase@example.com")
    
    user = db.query(User).filter(User.email == "statuscase@example.com").first()
    
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
    
    response = client.get(f"/api/v1/cases/{case.id}/status", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["case_id"] == case.id
    assert data["status"] == "ready"
