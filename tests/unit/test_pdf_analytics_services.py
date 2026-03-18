import pytest
from unittest.mock import MagicMock, patch
from sqlalchemy.orm import Session
from app.services.pdf_generator_service import PDFGeneratorService
from app.services.pdf_generator_service_fpdf2 import pdf_generator_service_fpdf2
from app.services.analytics_service import AnalyticsService
from app.models.case import Case
from app.models.extraction import ClinicalExtraction

@pytest.fixture
def pdf_generator():
    return PDFGeneratorService()

@pytest.fixture
def pdf_generator_fpdf2():
    return pdf_generator_service_fpdf2

@pytest.fixture
def analytics_service():
    return AnalyticsService()

@pytest.fixture
def mock_db():
    return MagicMock(spec=Session)

def test_generate_case_pdf_basic(pdf_generator):
    case = MagicMock(spec=Case)
    case.patient_name = "John Doe"
    case.case_number = "CASE-123"
    
    extraction = MagicMock(spec=ClinicalExtraction)
    extraction.extracted_data = {"diagnoses": [], "medications": [], "labs": []}
    extraction.summary = "Summary"
    extraction.timeline = []
    extraction.contradictions = []
    
    pdf_bytes = pdf_generator.generate_case_pdf(case, extraction, [])

    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 0
    assert b"%PDF" in pdf_bytes


def test_generate_case_pdf_fpdf2_basic(pdf_generator_fpdf2):
    """Test fpdf2 PDF generator returns valid PDF bytes (active generator)."""
    case = MagicMock(spec=Case)
    case.patient_name = "Jane Doe"
    case.case_number = "CASE-456"

    extraction = MagicMock(spec=ClinicalExtraction)
    extraction.extracted_data = {"diagnoses": [], "medications": [], "labs": [], "vitals_per_day_ranges": []}
    extraction.summary = "Clinical summary text."
    extraction.timeline = []
    extraction.executive_summary = None

    pdf_bytes = pdf_generator_fpdf2.generate_case_pdf(case, extraction, [])

    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 0
    assert b"%PDF" in pdf_bytes


def test_generate_case_pdf_fpdf2_with_timeline_and_meds(pdf_generator_fpdf2):
    """Test fpdf2 PDF generator with non-empty timeline and medications."""
    case = MagicMock(spec=Case)
    case.patient_name = "Test Patient"
    case.case_number = "CASE-789"

    extraction = MagicMock(spec=ClinicalExtraction)
    extraction.extracted_data = {
        "diagnoses": [{"name": "Hypertension"}],
        "medications": [
            {"name": "Lisinopril", "dosage": "10mg", "frequency": "daily", "start_date": "2025-01-01", "end_date": None},
        ],
        "labs": [],
        "vitals_per_day_ranges": [{"date": "2025-01-15", "bp": "120/80", "hr": "72", "spo2": "98", "temp": "98.6"}],
    }
    extraction.summary = "Summary"
    extraction.timeline = [
        {"date": "2025-01-10", "description": "Admission", "source": "ER"},
        {"date": "2025-01-12", "description": "Lab drawn", "source": "Nursing"},
    ]
    extraction.executive_summary = None

    pdf_bytes = pdf_generator_fpdf2.generate_case_pdf(case, extraction, [])

    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 0
    assert b"%PDF" in pdf_bytes


def test_track_evidence_click(analytics_service, mock_db):
    with patch.object(analytics_service.evidence_click_repo, "create") as mock_create:
        analytics_service.track_evidence_click(
            mock_db, "user-1", "case-1", "medication", "med-1", "file", file_id="f1", page_number=1
        )
        assert mock_create.called

def test_get_time_to_review_metrics(analytics_service, mock_db):
    # Mock query results to return empty list
    mock_query = mock_db.query.return_value
    mock_filter = mock_query.filter.return_value
    mock_filter.all.return_value = []
    
    # Mock the count query - handle the chain correctly
    with patch("app.services.analytics_service.and_", return_value=MagicMock()):
        metrics = analytics_service.get_time_to_review_metrics(mock_db, "user-1")
        # If the query chain is complex, we might just want to verify it doesn't crash
        assert isinstance(metrics, dict)
        assert "total_cases" in metrics
