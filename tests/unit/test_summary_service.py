import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from sqlalchemy.orm import Session
from app.services.summary_service import SummaryService

@pytest.fixture
def summary_service():
    return SummaryService()

@pytest.fixture
def mock_db():
    return MagicMock(spec=Session)

@pytest.mark.asyncio
async def test_generate_summary_success(summary_service, mock_db):
    extracted_data = {"diagnoses": [{"name": "Hypertension"}], "medications": [], "labs": []}
    timeline = []
    contradictions = []
    
    with patch.object(summary_service, "_get_llm_service") as mock_get_llm:
        mock_llm = AsyncMock()
        mock_llm.is_available.return_value = True
        mock_llm.chat_completion.return_value = ("Generated summary text", {"total_tokens": 100})
        mock_get_llm.return_value = mock_llm
        
        with patch("app.services.summary_service.prompt_service.render_prompt", return_value="Prompt"), \
             patch("app.services.summary_service.prompt_service.get_system_message", return_value="System"):
            
            summary = await summary_service.generate_summary(
                extracted_data, timeline, contradictions, "John Doe", "CASE-123",
                db=mock_db, case_id="case-1", user_id="user-1"
            )
            
            assert summary == "Generated summary text"
            assert mock_llm.chat_completion.called

@pytest.mark.asyncio
async def test_generate_summary_fallback(summary_service, mock_db):
    extracted_data = {"diagnoses": [], "medications": [], "labs": []}
    
    with patch.object(summary_service, "_get_llm_service") as mock_get_llm:
        mock_llm = MagicMock()
        mock_llm.is_available.return_value = False
        mock_get_llm.return_value = mock_llm
        
        summary = await summary_service.generate_summary(
            extracted_data, [], [], "John Doe", "CASE-123"
        )
        
        assert "John Doe" in summary
        assert "CASE-123" in summary
        assert "CLINICAL CASE SUMMARY" in summary
