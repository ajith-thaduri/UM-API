import pytest
from unittest.mock import MagicMock, patch
from sqlalchemy.orm import Session
from app.services.case_processor import CaseProcessor
from app.models.case import Case, CaseStatus
from app.models.case_file import CaseFile

@pytest.fixture
def case_processor():
    return CaseProcessor()

@pytest.fixture
def mock_db():
    return MagicMock(spec=Session)

def test_process_chunks_basic(case_processor, mock_db):
    case_id = "case-1"
    user_id = "user-1"
    case_file = MagicMock(spec=CaseFile)
    case_file.id = "file-1"
    case_files = [case_file]
    file_page_mapping = {"file-1": {1: "Page 1 text"}}
    
    mock_chunk = MagicMock()
    mock_chunk.chunk_text = "Page 1 text"
    mock_chunk.page_number = 1
    mock_chunk.token_count = 5
    
    with patch("app.services.case_processor.chunking_service.chunk_document", return_value=[mock_chunk]), \
         patch("app.services.case_processor.embedding_service.generate_embeddings_batch", return_value=[[0.1]*1536]), \
         patch("app.services.case_processor.chunk_repository.bulk_create") as mock_bulk_create:
        
            chunk_mapping = case_processor._process_chunks(mock_db, case_id, user_id, case_files, file_page_mapping)
    
            assert len(chunk_mapping) == 1
            assert mock_bulk_create.called

@pytest.mark.asyncio
async def test_process_case_not_found(case_processor, mock_db):
    with patch("app.services.case_processor.SessionLocal", return_value=mock_db):
        mock_db.query.return_value.filter.return_value.first.return_value = None
        
        result = await case_processor.process_case("missing-case")
        
        assert result["success"] is False
        assert "Case not found" in result["error"]
