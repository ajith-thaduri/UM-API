"""Unit tests for EntitySourceService"""

import pytest
from unittest.mock import MagicMock, patch
from sqlalchemy.orm import Session
from app.services.entity_source_service import EntitySourceService
from app.models.entity_source import EntitySource
from app.models.document_chunk import DocumentChunk, SectionType


@pytest.fixture
def entity_source_service():
    return EntitySourceService()


@pytest.fixture
def mock_db():
    return MagicMock(spec=Session)


@pytest.fixture
def mock_chunk():
    """Mock DocumentChunk"""
    chunk = MagicMock(spec=DocumentChunk)
    chunk.id = "chunk-1"
    chunk.file_id = "file-1"
    chunk.page_number = 5
    chunk.bbox = {"x0": 10, "y0": 20, "x1": 30, "y1": 40}
    chunk.chunk_text = "Test chunk text for entity source"
    return chunk


def test_create_entity_source_with_chunk_id(entity_source_service, mock_db, mock_chunk):
    """Test creating entity source with chunk_id"""
    with patch.object(entity_source_service.chunk_repo, "get_by_id", return_value=mock_chunk), \
         patch.object(entity_source_service.entity_source_repo, "get_by_entity", return_value=None):
        
        entity_source = entity_source_service.create_entity_source(
            db=mock_db,
            case_id="case-1",
            user_id="user-1",
            entity_type="medication",
            entity_id="medication:0",
            chunk_id="chunk-1"
        )
        
        assert isinstance(entity_source, EntitySource)
        assert entity_source.file_id == "file-1"
        assert entity_source.page_number == 5
        assert entity_source.bbox == {"x0": 10, "y0": 20, "x1": 30, "y1": 40}
        assert mock_db.add.called


def test_create_entity_source_without_chunk_id(entity_source_service, mock_db):
    """Test creating entity source with file_id and page_number"""
    with patch.object(entity_source_service.entity_source_repo, "get_by_entity", return_value=None):
        entity_source = entity_source_service.create_entity_source(
            db=mock_db,
            case_id="case-1",
            user_id="user-1",
            entity_type="lab",
            entity_id="lab:0",
            file_id="file-1",
            page_number=3,
            snippet="Lab result snippet"
        )
        
        assert isinstance(entity_source, EntitySource)
        assert entity_source.file_id == "file-1"
        assert entity_source.page_number == 3
        assert entity_source.snippet == "Lab result snippet"


def test_create_entity_source_missing_required_fields(entity_source_service, mock_db):
    """Test that missing file_id or page_number raises ValueError"""
    with pytest.raises(ValueError, match="Entity source requires file_id and page_number"):
        entity_source_service.create_entity_source(
            db=mock_db,
            case_id="case-1",
            user_id="user-1",
            entity_type="medication",
            entity_id="medication:0"
        )


def test_create_entity_source_updates_existing(entity_source_service, mock_db, mock_chunk):
    """Test that creating entity source updates existing record"""
    existing = EntitySource(
        id="existing-1",
        case_id="case-1",
        user_id="user-1",
        entity_type="medication",
        entity_id="medication:0",
        file_id="file-old",
        page_number=1
    )
    
    with patch.object(entity_source_service.entity_source_repo, "get_by_entity", return_value=existing):
        result = entity_source_service.create_entity_source(
            db=mock_db,
            case_id="case-1",
            user_id="user-1",
            entity_type="medication",
            entity_id="medication:0",
            file_id="file-new",
            page_number=2
        )
        
        assert result == existing
        assert existing.file_id == "file-new"
        assert existing.page_number == 2
        assert mock_db.flush.called


def test_get_entity_source(entity_source_service, mock_db):
    """Test getting entity source"""
    entity_source = EntitySource(
        id="source-1",
        case_id="case-1",
        user_id="user-1",
        entity_type="medication",
        entity_id="medication:0",
        file_id="file-1",
        page_number=1
    )
    
    with patch.object(entity_source_service.entity_source_repo, "get_by_entity", return_value=entity_source):
        result = entity_source_service.get_entity_source(
            db=mock_db,
            case_id="case-1",
            entity_type="medication",
            entity_id="medication:0",
            user_id="user-1"
        )
        
        assert result == entity_source


def test_create_sources_from_extraction(entity_source_service, mock_db):
    """Test creating entity sources from extraction results (uses bulk_create_entity_sources)."""
    extracted_data = {
        "medications": [
            {"name": "Aspirin", "source_file": "file-1", "source_page": 1},
            {"name": "Lisinopril", "source_file": "file-1", "source_page": 2}
        ],
        "labs": [
            {"test_name": "Creatinine", "source_file": "file-2", "source_page": 1}
        ],
        "diagnoses": [
            {"name": "Hypertension", "source_file": "file-1", "source_page": 3}
        ]
    }
    
    extraction_sources = [
        {"type": "medication", "chunk_id": "chunk-1", "file_id": "file-1", "page_number": 1},
        {"type": "medication", "chunk_id": "chunk-2", "file_id": "file-1", "page_number": 2},
        {"type": "lab", "chunk_id": "chunk-3", "file_id": "file-2", "page_number": 1},
        {"type": "diagnosis", "chunk_id": "chunk-4", "file_id": "file-1", "page_number": 3}
    ]
    
    file_lookup = {"file-1": "document1.pdf", "file-2": "document2.pdf"}
    
    with patch.object(entity_source_service, "bulk_create_entity_sources") as mock_bulk_create, \
         patch.object(entity_source_service.entity_source_repo, "count", return_value=0):
        mock_bulk_create.return_value = 4
        
        count = entity_source_service.create_sources_from_extraction(
            db=mock_db,
            case_id="case-1",
            user_id="user-1",
            extracted_data=extracted_data,
            extraction_sources=extraction_sources,
            file_lookup=file_lookup
        )
        
        assert mock_bulk_create.call_count == 1
        sources_passed = mock_bulk_create.call_args[0][1]
        assert len(sources_passed) >= 3
        assert count == 4


def test_validate_page_number_success(entity_source_service, mock_db):
    """Test successful page number validation"""
    source_mapping = {
        "file_page_mapping": {
            "file-1": {
                "1": "Page 1 text",
                "2": "Page 2 text",
                "3": "Page 3 text"
            }
        }
    }
    
    is_valid, max_page, error = entity_source_service.validate_page_number(
        db=mock_db,
        file_id="file-1",
        page_number=2,
        source_mapping=source_mapping
    )
    
    assert is_valid is True
    assert max_page == 3
    assert error is None


def test_validate_page_number_invalid(entity_source_service, mock_db):
    """Test page number validation with invalid page"""
    source_mapping = {
        "file_page_mapping": {
            "file-1": {
                "1": "Page 1 text",
                "2": "Page 2 text"
            }
        }
    }
    
    is_valid, max_page, error = entity_source_service.validate_page_number(
        db=mock_db,
        file_id="file-1",
        page_number=5,
        source_mapping=source_mapping
    )
    
    assert is_valid is False
    assert max_page == 2
    assert "exceeds maximum page" in error


def test_create_entity_source_with_validation(entity_source_service, mock_db):
    """Test creating entity source with validation"""
    source_mapping = {
        "file_page_mapping": {
            "file-1": {
                "1": "Page 1 text",
                "2": "Page 2 text"
            }
        }
    }
    
    with patch.object(entity_source_service, "create_entity_source", return_value=MagicMock(spec=EntitySource)):
        entity_source, error = entity_source_service.create_entity_source_with_validation(
            db=mock_db,
            case_id="case-1",
            user_id="user-1",
            entity_type="medication",
            entity_id="medication:0",
            file_id="file-1",
            page_number=1,
            source_mapping=source_mapping
        )
        
        assert entity_source is not None
        assert error is None


def test_create_entity_source_with_validation_fails(entity_source_service, mock_db):
    """Test creating entity source with validation fails for invalid page"""
    source_mapping = {
        "file_page_mapping": {
            "file-1": {
                "1": "Page 1 text"
            }
        }
    }
    
    entity_source, error = entity_source_service.create_entity_source_with_validation(
        db=mock_db,
        case_id="case-1",
        user_id="user-1",
        entity_type="medication",
        entity_id="medication:0",
        file_id="file-1",
        page_number=10,
        source_mapping=source_mapping
    )
    
    assert entity_source is None
    assert error is not None


def test_find_source_for_item_prefers_inline_file_page(entity_source_service):
    """Inline file/page metadata should override fragile index-based matching."""
    extraction_sources = [
        {"type": "lab", "chunk_id": "chunk-a", "file_id": "file-1", "page_number": 1},
        {"type": "lab", "chunk_id": "chunk-b", "file_id": "file-1", "page_number": 2},
    ]
    chunk_lookup = {
        "chunk-a": {"bbox": {"x0": 1, "y0": 1, "x1": 2, "y1": 2}},
        "chunk-b": {"bbox": {"x0": 3, "y0": 3, "x1": 4, "y1": 4}},
    }

    # Even though item_index=0 would normally pick chunk-a, preferred file/page
    # should force chunk-b.
    source = entity_source_service._find_source_for_item(
        extraction_sources=extraction_sources,
        source_type="lab",
        item_index=0,
        chunk_lookup=chunk_lookup,
        entity_name="WBC",
        preferred_file_id="file-1",
        preferred_page_number=2,
    )

    assert source is not None
    assert source.get("chunk_id") == "chunk-b"
    assert source.get("page_number") == 2
    assert source.get("bbox") == {"x0": 3, "y0": 3, "x1": 4, "y1": 4}


def test_create_sources_from_extraction_prefers_inline_source_fields(entity_source_service, mock_db):
    """Per-item source_file_id/source_page/bbox must win over mismatched source list."""
    extracted_data = {
        "medications": [],
        "diagnoses": [],
        "vitals": [],
        "labs": [
            {
                "test_name": "WBC",
                "value": "11.5",
                "date": "03/04/2025",
                "source_file_id": "file-correct",
                "source_page": 4,
                "bbox": {"x0": 10, "y0": 20, "x1": 30, "y1": 40},
            }
        ],
    }
    extraction_sources = [
        # Intentionally wrong page/source to ensure inline metadata is preferred.
        {"type": "lab", "chunk_id": "chunk-wrong", "file_id": "file-wrong", "page_number": 1}
    ]
    file_lookup = {"file-correct": "labs.pdf"}

    with patch.object(entity_source_service, "bulk_create_entity_sources") as mock_bulk_create, \
         patch.object(entity_source_service.entity_source_repo, "count", return_value=0):
        mock_bulk_create.return_value = 1
        entity_source_service.create_sources_from_extraction(
            db=mock_db,
            case_id="case-1",
            user_id="user-1",
            extracted_data=extracted_data,
            extraction_sources=extraction_sources,
            file_lookup=file_lookup,
        )

        assert mock_bulk_create.call_count == 1
        sources_passed = mock_bulk_create.call_args[0][1]
        assert len(sources_passed) == 1
        created = sources_passed[0]
        assert created["entity_type"] == "lab"
        assert created["entity_id"] == "lab:0"
        assert created["file_id"] == "file-correct"
        assert created["page_number"] == 4
        assert created["bbox"] == {"x0": 10, "y0": 20, "x1": 30, "y1": 40}
