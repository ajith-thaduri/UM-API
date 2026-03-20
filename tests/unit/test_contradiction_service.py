import pytest
from datetime import datetime
from app.services.contradiction_service import ContradictionService

@pytest.fixture
def contradiction_service():
    return ContradictionService()

def test_detect_duplicates(contradiction_service):
    mock_timeline = [
        {"id": "1", "date": "2024-01-01", "event_type": "lab", "description": "Blood Test"},
        {"id": "2", "date": "2024-01-01", "event_type": "lab", "description": "Blood Test"} # Duplicate
    ]
    
    issues = contradiction_service._detect_duplicates(mock_timeline)
    assert len(issues) == 1
    assert issues[0]["type"] == "duplicate_entry"
    assert "Blood Test" in issues[0]["description"]

def test_detect_missing_expected_data(contradiction_service):
    # Empty extracted data should trigger "missing data" alerts
    mock_extracted_data = {
        "diagnoses": [],
        "medications": [],
        "procedures": []
    }
    
    issues = contradiction_service._detect_missing_expected_data(mock_extracted_data)
    assert len(issues) > 0
    # Should flag missing critical sections
    types = [issue["type"] for issue in issues]
    assert "missing_information" in types

def test_detect_conflicts_blood_type(contradiction_service):
    mock_extracted_data = {
        "labs": [
            {"test_name": "Blood Type", "value": "A+"},
            {"test_name": "Blood Type", "value": "B-"} # Conflict
        ]
    }
    
    issues = contradiction_service._detect_conflicts(mock_extracted_data)
    # Filter for blood type conflict
    blood_conflicts = [i for i in issues if "blood type" in i["description"].lower()]
    assert len(blood_conflicts) > 0


# ==================== Chronological Error Detection Tests ====================

def test_detect_date_mismatch_basic_error(contradiction_service):
    """Test basic chronological error: discharge before admission"""
    timeline = [
        {"id": "1", "date": "01/15/2024", "event_type": "discharge", "description": "Patient discharged"},
        {"id": "2", "date": "01/20/2024", "event_type": "admission", "description": "Patient admitted"}
    ]
    
    errors = contradiction_service._detect_date_mismatches(timeline)
    assert len(errors) == 1
    assert errors[0]["type"] == "chronological_error"
    assert "Discharge documented on 01/15/2024" in errors[0]["description"]
    assert "Admission on 01/20/2024" in errors[0]["description"]


def test_detect_date_mismatch_valid_order(contradiction_service):
    """Test valid chronological order: admission before discharge"""
    timeline = [
        {"id": "1", "date": "01/15/2024", "event_type": "admission", "description": "Patient admitted"},
        {"id": "2", "date": "01/20/2024", "event_type": "discharge", "description": "Patient discharged"}
    ]
    
    errors = contradiction_service._detect_date_mismatches(timeline)
    assert len(errors) == 0


def test_detect_date_mismatch_same_day(contradiction_service):
    """Test same-day admission/discharge should NOT be flagged as error"""
    timeline = [
        {"id": "1", "date": "01/15/2024", "event_type": "admission", "description": "Patient admitted"},
        {"id": "2", "date": "01/15/2024", "event_type": "discharge", "description": "Patient discharged"}
    ]
    
    errors = contradiction_service._detect_date_mismatches(timeline)
    assert len(errors) == 0


def test_detect_date_mismatch_multiple_pairs_valid(contradiction_service):
    """Test multiple admission/discharge pairs with correct order"""
    timeline = [
        {"id": "1", "date": "01/01/2024", "event_type": "admission", "description": "Patient admitted"},
        {"id": "2", "date": "01/05/2024", "event_type": "discharge", "description": "Patient discharged"},
        {"id": "3", "date": "01/10/2024", "event_type": "admission", "description": "Patient admitted"},
        {"id": "4", "date": "01/15/2024", "event_type": "discharge", "description": "Patient discharged"}
    ]
    
    errors = contradiction_service._detect_date_mismatches(timeline)
    assert len(errors) == 0


def test_detect_date_mismatch_multiple_pairs_error(contradiction_service):
    """Test multiple pairs with error in second pair"""
    timeline = [
        {"id": "1", "date": "01/01/2024", "event_type": "admission", "description": "Patient admitted"},
        {"id": "2", "date": "01/05/2024", "event_type": "discharge", "description": "Patient discharged"},
        {"id": "3", "date": "01/10/2024", "event_type": "admission", "description": "Patient admitted"},
        {"id": "4", "date": "01/03/2024", "event_type": "discharge", "description": "Patient discharged"}  # Error: before second admission
    ]
    
    errors = contradiction_service._detect_date_mismatches(timeline)
    # Should detect error: discharge 01/03/2024 is before admission 01/10/2024
    # May also detect discharge 01/05/2024 before admission 01/10/2024 (both are errors)
    assert len(errors) >= 1
    # Check that the main error is detected
    error_dates = [err["description"] for err in errors]
    assert any("01/03/2024" in desc and "01/10/2024" in desc for desc in error_dates)


def test_detect_date_mismatch_date_formats(contradiction_service):
    """Test detection works with various date formats"""
    # Test YYYY-MM-DD format
    timeline_iso = [
        {"id": "1", "date": "2024-01-15", "event_type": "discharge", "description": "Patient discharged"},
        {"id": "2", "date": "2024-01-20", "event_type": "admission", "description": "Patient admitted"}
    ]
    errors = contradiction_service._detect_date_mismatches(timeline_iso)
    assert len(errors) == 1
    
    # Test MM/DD/YYYY format
    timeline_us = [
        {"id": "1", "date": "01/15/2024", "event_type": "discharge", "description": "Patient discharged"},
        {"id": "2", "date": "01/20/2024", "event_type": "admission", "description": "Patient admitted"}
    ]
    errors = contradiction_service._detect_date_mismatches(timeline_us)
    assert len(errors) == 1
    
    # Test "January 15, 2024" format
    timeline_text = [
        {"id": "1", "date": "January 15, 2024", "event_type": "discharge", "description": "Patient discharged"},
        {"id": "2", "date": "January 20, 2024", "event_type": "admission", "description": "Patient admitted"}
    ]
    errors = contradiction_service._detect_date_mismatches(timeline_text)
    assert len(errors) == 1


def test_detect_date_mismatch_event_type_priority(contradiction_service):
    """Test that event_type is used primarily, description is fallback"""
    # Event with event_type="admission" but description doesn't contain "admission"
    timeline = [
        {"id": "1", "date": "01/15/2024", "event_type": "discharge", "description": "Patient visit"},
        {"id": "2", "date": "01/20/2024", "event_type": "admission", "description": "Patient visit"}
    ]
    
    errors = contradiction_service._detect_date_mismatches(timeline)
    assert len(errors) == 1  # Should detect using event_type
    
    # Event with description fallback (no event_type)
    timeline_fallback = [
        {"id": "1", "date": "01/15/2024", "description": "Patient discharged"},
        {"id": "2", "date": "01/20/2024", "description": "Patient admitted"}
    ]
    
    errors = contradiction_service._detect_date_mismatches(timeline_fallback)
    assert len(errors) == 1  # Should detect using description


def test_detect_date_mismatch_missing_dates(contradiction_service):
    """Test that events without dates are skipped gracefully"""
    timeline = [
        {"id": "1", "event_type": "admission", "description": "Patient admitted"},  # No date
        {"id": "2", "date": "01/20/2024", "event_type": "discharge", "description": "Patient discharged"},
        {"id": "3", "date": "", "event_type": "admission", "description": "Patient admitted"},  # Empty date
        {"id": "4", "date": None, "event_type": "discharge", "description": "Patient discharged"}  # None date
    ]
    
    errors = contradiction_service._detect_date_mismatches(timeline)
    # Should not crash and should only process events with valid dates
    assert isinstance(errors, list)


def test_detect_date_mismatch_mixed_event_types(contradiction_service):
    """Test that only admission/discharge events are checked"""
    timeline = [
        {"id": "1", "date": "01/01/2024", "event_type": "lab_result", "description": "Blood test"},
        {"id": "2", "date": "01/05/2024", "event_type": "discharge", "description": "Patient discharged"},
        {"id": "3", "date": "01/10/2024", "event_type": "admission", "description": "Patient admitted"},
        {"id": "4", "date": "01/15/2024", "event_type": "procedure", "description": "Surgery"},
        {"id": "5", "date": "01/20/2024", "event_type": "vital_recorded", "description": "Blood pressure"}
    ]
    
    errors = contradiction_service._detect_date_mismatches(timeline)
    assert len(errors) == 1  # Should detect error between discharge and admission


def test_detect_date_mismatch_no_errors(contradiction_service):
    """Test timeline with no chronological errors"""
    timeline = [
        {"id": "1", "date": "01/01/2024", "event_type": "admission", "description": "Patient admitted"},
        {"id": "2", "date": "01/05/2024", "event_type": "discharge", "description": "Patient discharged"}
    ]
    
    errors = contradiction_service._detect_date_mismatches(timeline)
    assert len(errors) == 0


def test_detect_date_mismatch_sources_extracted(contradiction_service):
    """Test that source information is correctly extracted"""
    timeline = [
        {
            "id": "1", 
            "date": "01/15/2024", 
            "event_type": "discharge", 
            "description": "Patient discharged",
            "source_file": "file1.pdf",
            "source_page": 5
        },
        {
            "id": "2", 
            "date": "01/20/2024", 
            "event_type": "admission", 
            "description": "Patient admitted",
            "source_file": "file2.pdf",
            "source_page": 10
        }
    ]
    
    errors = contradiction_service._detect_date_mismatches(timeline)
    assert len(errors) == 1
    assert len(errors[0]["sources"]) == 2
    # affected_events order: [admission_id, discharge_id] per original behavior
    assert errors[0]["affected_events"] == ["2", "1"]  # admission=2, discharge=1
