import pytest
from fastapi import status
from app.models.user import User
from app.models.case import Case, CaseStatus, Priority
from app.models.extraction import ClinicalExtraction

def get_auth_headers(client, email="extractions@example.com", password="password123"):
    """Helper to register and get auth token."""
    reg_data = {"email": email, "password": password, "name": "Test User"}
    response = client.post("/api/v1/auth/register", json=reg_data)
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}

def test_get_extraction(client, db):
    """Test getting extraction for a case."""
    headers = get_auth_headers(client, "getextraction@example.com")
    
    user = db.query(User).filter(User.email == "getextraction@example.com").first()
    
    # Create case
    case = Case(
        id="extraction-case-1",
        patient_id="PAT-001",
        patient_name="Test Patient",
        case_number="CASE-EXT-1",
        status=CaseStatus.READY,
        priority=Priority.NORMAL,
        user_id=user.id
    )
    db.add(case)
    
    # Create extraction
    extraction = ClinicalExtraction(
        id="extraction-1",
        case_id=case.id,
        user_id=user.id,
        extracted_data={"diagnoses": ["Test Diagnosis"]},
        summary="Test summary"
    )
    db.add(extraction)
    db.commit()
    
    response = client.get(f"/api/v1/extractions/{case.id}", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["case_id"] == case.id

def test_get_extraction_not_found(client, db):
    """Test getting extraction for non-existent case."""
    headers = get_auth_headers(client, "noextraction@example.com")
    response = client.get("/api/v1/extractions/non-existent-case", headers=headers)
    assert response.status_code == status.HTTP_404_NOT_FOUND

def test_get_timeline(client, db):
    """Test getting timeline for a case."""
    headers = get_auth_headers(client, "timeline@example.com")
    
    user = db.query(User).filter(User.email == "timeline@example.com").first()
    
    case = Case(
        id="timeline-case-1",
        patient_id="PAT-002",
        patient_name="Timeline Patient",
        case_number="CASE-TIMELINE-1",
        status=CaseStatus.READY,
        priority=Priority.NORMAL,
        user_id=user.id
    )
    db.add(case)
    
    extraction = ClinicalExtraction(
        id="timeline-extraction-1",
        case_id=case.id,
        user_id=user.id,
        extracted_data={"diagnoses": ["Test"]},
        timeline=[{"date": "01/01/2024", "event": "Test event"}],
        timeline_summary=[{"date": "01/01/2024", "event": "Summary event"}]
    )
    db.add(extraction)
    db.commit()
    
    response = client.get(f"/api/v1/extractions/{case.id}/timeline", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    assert "timeline" in response.json()

def test_get_timeline_summary_level(client, db):
    """Test getting timeline with summary level."""
    headers = get_auth_headers(client, "timelinesummary@example.com")
    
    user = db.query(User).filter(User.email == "timelinesummary@example.com").first()
    
    case = Case(
        id="summary-case-1",
        patient_id="PAT-003",
        patient_name="Summary Patient",
        case_number="CASE-SUMMARY-1",
        status=CaseStatus.READY,
        priority=Priority.NORMAL,
        user_id=user.id
    )
    db.add(case)
    
    extraction = ClinicalExtraction(
        id="summary-extraction-1",
        case_id=case.id,
        user_id=user.id,
        extracted_data={"diagnoses": ["Test"]},
        timeline_summary=[{"date": "01/01/2024", "event": "Summary"}]
    )
    db.add(extraction)
    db.commit()
    
    response = client.get(f"/api/v1/extractions/{case.id}/timeline?level=summary", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["level"] == "summary"

def test_get_timelines(client, db):
    """Test getting both timelines."""
    headers = get_auth_headers(client, "timelines@example.com")
    
    user = db.query(User).filter(User.email == "timelines@example.com").first()
    
    case = Case(
        id="timelines-case-1",
        patient_id="PAT-004",
        patient_name="Timelines Patient",
        case_number="CASE-TIMELINES-1",
        status=CaseStatus.READY,
        priority=Priority.NORMAL,
        user_id=user.id
    )
    db.add(case)
    
    extraction = ClinicalExtraction(
        id="timelines-extraction-1",
        case_id=case.id,
        user_id=user.id,
        extracted_data={"diagnoses": ["Test"]},
        timeline=[{"date": "01/01/2024", "event": "Detailed"}],
        timeline_summary=[{"date": "01/01/2024", "event": "Summary"}]
    )
    db.add(extraction)
    db.commit()
    
    response = client.get(f"/api/v1/extractions/{case.id}/timelines", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    assert "summary" in response.json()
    assert "detailed" in response.json()

def test_get_contradictions(client, db):
    """Test getting contradictions."""
    headers = get_auth_headers(client, "contradictions@example.com")
    
    user = db.query(User).filter(User.email == "contradictions@example.com").first()
    
    case = Case(
        id="contradictions-case-1",
        patient_id="PAT-005",
        patient_name="Contradictions Patient",
        case_number="CASE-CONT-1",
        status=CaseStatus.READY,
        priority=Priority.NORMAL,
        user_id=user.id
    )
    db.add(case)
    
    extraction = ClinicalExtraction(
        id="contradictions-extraction-1",
        case_id=case.id,
        user_id=user.id,
        extracted_data={"diagnoses": ["Test"]},
        contradictions=[{"type": "medication", "description": "Test contradiction"}]
    )
    db.add(extraction)
    db.commit()
    
    response = client.get(f"/api/v1/extractions/{case.id}/contradictions", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    assert "contradictions" in response.json()

def test_get_summary(client, db):
    """Test getting summary."""
    headers = get_auth_headers(client, "summary@example.com")
    
    user = db.query(User).filter(User.email == "summary@example.com").first()
    
    case = Case(
        id="summary-case-2",
        patient_id="PAT-006",
        patient_name="Summary Patient 2",
        case_number="CASE-SUM-2",
        status=CaseStatus.READY,
        priority=Priority.NORMAL,
        user_id=user.id
    )
    db.add(case)
    
    extraction = ClinicalExtraction(
        id="summary-extraction-2",
        case_id=case.id,
        user_id=user.id,
        extracted_data={"diagnoses": ["Test"]},
        summary="This is a test summary"
    )
    db.add(extraction)
    db.commit()
    
    response = client.get(f"/api/v1/extractions/{case.id}/summary", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    assert "summary" in response.json()
