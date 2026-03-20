"""Unit tests for EvidenceSignalsService"""

import pytest
from app.services.evidence_signals_service import EvidenceSignalsService


@pytest.fixture
def evidence_signals_service():
    return EvidenceSignalsService()


def test_extract_iv_to_po_transitions(evidence_signals_service):
    """Test extraction of IV to PO medication transitions"""
    extracted_data = {
        "medications": [
            {
                "name": "Vancomycin",
                "route": "IV",
                "start_date": "01/01/2024",
                "dosage": "1g",
                "source_file": "file1.pdf",
                "source_page": 1
            },
            {
                "name": "Vancomycin",
                "route": "PO",
                "start_date": "01/05/2024",
                "dosage": "500mg",
                "source_file": "file1.pdf",
                "source_page": 2
            }
        ]
    }
    
    signals = evidence_signals_service.extract_signals(extracted_data)
    
    iv_to_po_signals = [s for s in signals if s["signal_type"] == "iv_to_po"]
    assert len(iv_to_po_signals) >= 1
    assert iv_to_po_signals[0]["description"] == "Vancomycin: Route changed from IV to PO"
    assert iv_to_po_signals[0]["source"] == "medications"


def test_extract_room_air_transitions(evidence_signals_service):
    """Test extraction of room air transitions"""
    extracted_data = {
        "vitals": [
            {
                "type": "Oxygen",
                "value": "2L",
                "unit": "NC",
                "date": "01/01/2024",
                "notes": "Nasal cannula",
                "source_file": "file1.pdf",
                "source_page": 1
            },
            {
                "type": "Oxygen",
                "value": "Room Air",
                "unit": "",
                "date": "01/05/2024",
                "notes": "Discontinued oxygen",
                "source_file": "file1.pdf",
                "source_page": 2
            }
        ]
    }
    
    signals = evidence_signals_service.extract_signals(extracted_data)
    
    room_air_signals = [s for s in signals if s["signal_type"] == "room_air"]
    assert len(room_air_signals) >= 1
    assert "room air" in room_air_signals[0]["description"].lower()
    assert room_air_signals[0]["source"] == "vitals"


def test_extract_ambulation_signals(evidence_signals_service):
    """Test extraction of ambulation signals"""
    extracted_data = {
        "procedures": [
            {
                "name": "Physical Therapy",
                "date": "01/10/2024",
                "notes": "Patient ambulated 50 feet",
                "source_file": "file1.pdf",
                "source_page": 1
            },
            {
                "name": "Mobility Assessment",
                "date": "01/12/2024",
                "notes": "Up to chair with assistance",
                "source_file": "file1.pdf",
                "source_page": 2
            }
        ]
    }
    
    signals = evidence_signals_service.extract_signals(extracted_data)
    
    ambulation_signals = [s for s in signals if s["signal_type"] == "ambulation"]
    assert len(ambulation_signals) >= 2
    assert all(s["source"] == "procedures" for s in ambulation_signals)


def test_extract_signals_empty_data(evidence_signals_service):
    """Test extraction with empty data"""
    extracted_data = {}
    signals = evidence_signals_service.extract_signals(extracted_data)
    assert signals == []


def test_extract_signals_with_timeline(evidence_signals_service):
    """Test extraction with timeline data"""
    extracted_data = {
        "vitals": []
    }
    
    timeline = [
        {
            "date": "01/05/2024",
            "description": "Patient on room air, oxygen discontinued",
            "event_type": "vital",
            "source": "vitals",
            "source_file": "file1.pdf",
            "source_page": 1
        },
        {
            "date": "01/10/2024",
            "description": "Physical therapy - patient ambulated",
            "event_type": "procedure",
            "source": "procedures",
            "source_file": "file1.pdf",
            "source_page": 2
        }
    ]
    
    signals = evidence_signals_service.extract_signals(extracted_data, timeline)
    
    assert len(signals) >= 2
    signal_types = {s["signal_type"] for s in signals}
    assert "room_air" in signal_types or "ambulation" in signal_types


def test_extract_signals_sorted_by_date(evidence_signals_service):
    """Test that signals are sorted by date"""
    extracted_data = {
        "medications": [
            {
                "name": "Medication A",
                "route": "IV",
                "start_date": "01/10/2024"
            },
            {
                "name": "Medication A",
                "route": "PO",
                "start_date": "01/05/2024"
            }
        ]
    }
    
    signals = evidence_signals_service.extract_signals(extracted_data)
    
    # Should be sorted by date
    dates = [s.get("date") for s in signals if s.get("date")]
    if len(dates) > 1:
        # Dates should be in chronological order (after parsing)
        assert dates == sorted(dates, key=lambda x: evidence_signals_service._parse_date_for_sort(x))


def test_extract_iv_to_po_multiple_medications(evidence_signals_service):
    """Test IV to PO extraction with multiple medications"""
    extracted_data = {
        "medications": [
            {
                "name": "Vancomycin",
                "route": "IV",
                "start_date": "01/01/2024"
            },
            {
                "name": "Vancomycin",
                "route": "PO",
                "start_date": "01/05/2024"
            },
            {
                "name": "Ciprofloxacin",
                "route": "IV",
                "start_date": "01/02/2024"
            },
            {
                "name": "Ciprofloxacin",
                "route": "PO",
                "start_date": "01/06/2024"
            }
        ]
    }
    
    signals = evidence_signals_service.extract_signals(extracted_data)
    
    iv_to_po_signals = [s for s in signals if s["signal_type"] == "iv_to_po"]
    assert len(iv_to_po_signals) >= 2


def test_extract_room_air_keywords(evidence_signals_service):
    """Test room air detection with various keywords"""
    extracted_data = {
        "vitals": [
            {
                "type": "Oxygen",
                "value": "Room Air",
                "date": "01/05/2024"
            },
            {
                "type": "O2",
                "value": "RA",
                "date": "01/06/2024"
            },
            {
                "type": "Respiratory",
                "notes": "No oxygen",
                "date": "01/07/2024"
            }
        ]
    }
    
    signals = evidence_signals_service.extract_signals(extracted_data)
    
    room_air_signals = [s for s in signals if s["signal_type"] == "room_air"]
    assert len(room_air_signals) >= 1


def test_extract_ambulation_keywords(evidence_signals_service):
    """Test ambulation detection with various keywords"""
    extracted_data = {
        "procedures": [
            {
                "name": "PT",
                "notes": "Patient ambulated",
                "date": "01/10/2024"
            },
            {
                "name": "Mobility",
                "notes": "Up to chair",
                "date": "01/11/2024"
            },
            {
                "name": "Physical Therapy",
                "notes": "Walking with assistance",
                "date": "01/12/2024"
            }
        ]
    }
    
    signals = evidence_signals_service.extract_signals(extracted_data)
    
    ambulation_signals = [s for s in signals if s["signal_type"] == "ambulation"]
    assert len(ambulation_signals) >= 3
