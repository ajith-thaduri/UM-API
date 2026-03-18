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
    
    with patch("app.services.summary_service.settings") as mock_settings, \
         patch.object(summary_service, "_get_tier2_llm_service") as mock_get_llm:
        
        mock_settings.ENABLE_TWO_TIER_ARCHITECTURE = True
        mock_llm = AsyncMock()
        mock_llm.is_available.return_value = True
        mock_llm.chat_completion.return_value = ("Generated summary text", {"total_tokens": 100})
        mock_get_llm.return_value = mock_llm
        
        de_id_payload = {
            "clinical_data": extracted_data,
            "timeline": timeline,
            "red_flags": contradictions,
            "document_chunks": []
        }
        
        with patch("app.services.summary_service.presidio_deidentification_service.de_identify_for_summary", 
                   return_value=(de_id_payload, "vault-1", {"[[PERSON-01]]": "John Doe"})), \
             patch("app.services.summary_service.presidio_deidentification_service.re_identify_summary", 
                   return_value="Generated summary text"), \
             patch("app.services.summary_service.prompt_service.render_prompt", return_value="Prompt"), \
             patch("app.services.summary_service.prompt_service.get_system_message", return_value="System"), \
             patch.object(summary_service._pref_repo, "get_by_user_id", return_value=None):
            
            summary = await summary_service.generate_summary(
                extracted_data, timeline, contradictions, "John Doe", "CASE-123",
                db=mock_db, case_id="case-1", user_id="user-1"
            )
            
            assert summary == "Generated summary text"
            assert mock_llm.chat_completion.called

@pytest.mark.asyncio
async def test_generate_summary_with_chunks(summary_service, mock_db):
    extracted_data = {"diagnoses": [], "medications": [], "labs": []}
    timeline = []
    contradictions = []
    document_chunks = ["Patient John Doe was admitted on 01/01/2024."]
    
    with patch("app.services.summary_service.settings") as mock_settings, \
         patch.object(summary_service, "_get_tier2_llm_service") as mock_get_llm:
        
        mock_settings.ENABLE_TWO_TIER_ARCHITECTURE = True
        mock_llm = AsyncMock()
        mock_llm.is_available.return_value = True
        mock_llm.chat_completion.return_value = ("Summary with chunks", {"total_tokens": 150})
        mock_get_llm.return_value = mock_llm
        
        # Mock de-identification to return document_chunks in payload
        de_id_payload = {
            "clinical_data": extracted_data,
            "timeline": timeline,
            "red_flags": contradictions,
            "document_chunks": ["[[PERSON-01]] was admitted on 01/01/2024."]
        }
        
        with patch("app.services.summary_service.presidio_deidentification_service.de_identify_for_summary", 
                   return_value=(de_id_payload, "vault-1", {"[[PERSON-01]]": "John Doe"})), \
             patch("app.services.summary_service.presidio_deidentification_service.re_identify_summary", 
                   return_value="Re-identified Summary"), \
             patch("app.services.summary_service.prompt_service.render_prompt", return_value="Prompt"), \
             patch("app.services.summary_service.prompt_service.get_system_message", return_value="System"), \
             patch.object(summary_service._pref_repo, "get_by_user_id", return_value=None):
            
            summary = await summary_service.generate_summary(
                extracted_data, timeline, contradictions, "John Doe", "CASE-123",
                db=mock_db, case_id="case-1", user_id="user-1",
                document_chunks=document_chunks
            )
            
            # Verify that clinical variables in variables dict would have been placeholders
            # (In reality, we mock the render_prompt, but we can verify the logic if we didn't mock it)
            # For now, just ensure the flow still works.
            assert summary == "Re-identified Summary"
            assert mock_llm.chat_completion.called

@pytest.mark.asyncio
async def test_generate_summary_fallback(summary_service, mock_db):
    extracted_data = {"diagnoses": [], "medications": [], "labs": []}
    
    with patch("app.services.summary_service.settings") as mock_settings, \
         patch.object(summary_service, "_get_tier2_llm_service") as mock_get_llm:
        
        mock_settings.ENABLE_TWO_TIER_ARCHITECTURE = True
        mock_llm = AsyncMock()
        mock_llm.is_available.return_value = False
        mock_get_llm.return_value = mock_llm
        
        with patch.object(summary_service._pref_repo, "get_by_user_id", return_value=None):
            summary = await summary_service.generate_summary(
                extracted_data, [], [], "John Doe", "CASE-123",
                db=mock_db, case_id="case-1", user_id="user-1"
            )
            
            assert "John Doe" in summary
            assert "CASE-123" in summary
            assert "CLINICAL CASE SUMMARY" in summary

