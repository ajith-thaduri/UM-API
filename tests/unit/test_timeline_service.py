import pytest
from app.services.timeline_service import TimelineService
from datetime import datetime
from unittest.mock import patch

@pytest.fixture
def timeline_service():
    return TimelineService()

def test_build_timeline_basic(timeline_service):
    # Mock data representing extracted clinical info
    # Note: timeline service filters out events without source_file/source_page
    mock_extracted_data = {
        "diagnoses": [{"date": "2024-01-01", "name": "Diabetes", "source_file": "f1", "source_page": 1}],
        "medications": [{"date": "2024-01-02", "name": "Metformin", "source_file": "f1", "source_page": 1}],
        "procedures": [{"date": "2024-01-03", "name": "Surgery", "source_file": "f1", "source_page": 1}],
        "labs": [{"date": "2024-01-04", "test_name": "Glucose", "value": "120", "source_file": "f1", "source_page": 1}],
        "vitals": [{"date": "2024-01-05", "type": "BP", "value": "120/80", "source_file": "f1", "source_page": 1}],
        "imaging": [{"date": "2024-01-06", "name": "X-Ray", "source_file": "f1", "source_page": 1}],
        "therapy_notes": [{"date": "2024-01-07", "type": "PT", "description": "Walking", "source_file": "f1", "source_page": 1}]
    }
    
    result = timeline_service.build_timeline(mock_extracted_data, "raw text")
    
    assert "detailed" in result
    assert "summary" in result
    assert len(result["detailed"]) == 7
    # Verify chronological order
    dates = [event["date"] for event in result["detailed"]]
    assert dates == sorted(dates)

def test_categorize_medications(timeline_service):
    mock_meds = [
        {"name": "Med A", "date": "01/01/2024", "description": "home medication"}, # Admission Home
        {"name": "Med B", "date": "01/05/2024"}, # Inpatient
        {"name": "Med C", "date": "01/10/2024"}  # Discharge
    ]
    mock_timeline = [
        {"date": "01/01/2024", "event_type": "admission", "description": "Admitted"},
        {"date": "01/10/2024", "event_type": "discharge", "description": "Discharged"}
    ]
    
    categories = timeline_service.categorize_medications(mock_meds, mock_timeline)
    
    assert "admission_home" in categories
    assert "inpatient" in categories
    assert "discharge" in categories
    assert any(m["name"] == "Med A" for m in categories["admission_home"])
    assert any(m["name"] == "Med B" for m in categories["inpatient"])
    assert any(m["name"] == "Med C" for m in categories["discharge"])

def test_compute_vitals_per_day_ranges(timeline_service):
    mock_vitals = [
        {"date": "01/01/2024", "type": "Heart Rate", "value": "70", "unit": "bpm"},
        {"date": "01/01/2024", "type": "Heart Rate", "value": "90", "unit": "bpm"},
        {"date": "01/02/2024", "type": "Heart Rate", "value": "75", "unit": "bpm"}
    ]
    mock_timeline = [
        {"date": "01/01/2024", "event_type": "admission", "description": "Admitted"}
    ]
    
    vitals_per_day = timeline_service.compute_vitals_per_day_ranges(mock_vitals, mock_timeline)
    
    # Check Jan 1, 2024
    day1_key = "01/01/2024"
    assert day1_key in vitals_per_day
    # Ensure it's a dict and not the string "Range not available"
    assert isinstance(vitals_per_day[day1_key]["heart_rate"], dict)
    assert vitals_per_day[day1_key]["heart_rate"]["min"] == 70
    assert vitals_per_day[day1_key]["heart_rate"]["max"] == 90


def test_filter_events_without_sources_accepts_source_file_id(timeline_service):
    events = [
        {
            "id": "evt-1",
            "date": "01/01/2024",
            "event_type": "diagnosis",
            "description": "Diagnosed: CHF",
            "details": {"source_file_id": "file-123", "source_page": 2},
        }
    ]

    filtered = timeline_service._filter_events_without_sources(events)

    assert len(filtered) == 1


def test_build_timeline_includes_rag_supplement_when_available(timeline_service):
    supplement = [
        {
            "id": "evt-s1",
            "date": "01/03/2024",
            "event_type": "diagnosis",
            "description": "Diagnosed: Pneumonia",
            "source_file": "file-1",
            "source_page": 3,
            "details": {"rag_extracted": True},
        }
    ]

    def _mock_run(coro):
        coro.close()
        return supplement

    with patch.object(
        timeline_service,
        "_run_async_in_sync_context",
        side_effect=_mock_run,
    ) as mock_runner:
        result = timeline_service.build_timeline(
            extracted_data={"medications": [], "diagnoses": []},
            raw_text="",
            db=object(),
            case_id="case-1",
            user_id="user-1",
        )

    mock_runner.assert_called_once()
    assert len(result["detailed"]) == 1
    assert result["detailed"][0]["description"] == "Diagnosed: Pneumonia"
