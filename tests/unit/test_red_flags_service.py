import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from sqlalchemy.orm import Session
from app.services.red_flags_service import MissingInfoService

@pytest.fixture
def red_flags_service():
    return MissingInfoService()

@pytest.fixture
def mock_db():
    return MagicMock(spec=Session)

@pytest.mark.asyncio
async def test_detect_success(red_flags_service, mock_db):
    clinical_data = {"diagnoses": ["Hypertension"], "medications": [], "imaging": []}
    
    with patch.object(red_flags_service, "_get_llm_service") as mock_get_llm:
        mock_llm = AsyncMock()
        mock_llm.is_available.return_value = True
        mock_llm.chat_completion.return_value = ('{"gaps": [{"type": "missing_imaging", "description": "Missing MRI"}]}', {"total_tokens": 50})
        mock_get_llm.return_value = mock_llm
        
        with patch("app.services.red_flags_service.prompt_service.render_prompt", return_value="Prompt"), \
             patch("app.services.red_flags_service.prompt_service.get_system_message", return_value="System"), \
             patch("app.services.red_flags_service.settings") as mock_settings:
            
            mock_settings.CLAUDE_MODEL = "claude-3"
            
            gaps = await red_flags_service.detect(clinical_data, db=mock_db, user_id="user-1")
            
            assert len(gaps) == 1
            assert gaps[0]["type"] == "missing_info"

@pytest.mark.asyncio
async def test_detect_fallback(red_flags_service, mock_db):
    clinical_data = {"diagnoses": [], "medications": [], "imaging": []}
    
    with patch.object(red_flags_service, "_get_llm_service") as mock_get_llm:
        mock_llm = MagicMock()
        mock_llm.is_available.return_value = False
        mock_get_llm.return_value = mock_llm
        
        gaps = await red_flags_service.detect(clinical_data)
        
        # Heuristic fallback should return empty list for empty data
        assert isinstance(gaps, list)
