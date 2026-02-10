import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from app.services.llm_service import LLMService

class TestLLMService:
    @pytest.fixture
    def service(self):
        return LLMService()

    def test_get_mock_extraction(self, service):
        """Test mock extraction fallback"""
        result = service._get_mock_extraction()
        assert "diagnoses" in result
        assert "medications" in result
        assert len(result["diagnoses"]) > 0

    @pytest.mark.asyncio
    async def test_extract_clinical_information_no_api_key(self, service):
        """Test fallback to mock when LLM is unavailable"""
        mock_llm = MagicMock()
        mock_llm.is_available.return_value = False
        
        with patch.object(service, '_get_llm_service', return_value=mock_llm):
            result = await service.extract_clinical_information("Some medical text")
            assert "diagnoses" in result
            assert "Type 2 Diabetes Mellitus" in result["diagnoses"]

    @pytest.mark.asyncio
    async def test_extract_clinical_information_success(self, service):
        """Test successful LLM extraction"""
        mock_llm = AsyncMock()
        mock_llm.is_available.return_value = True
        mock_llm.chat_completion.return_value = (
            '{"diagnoses": ["Asthma"], "medications": []}',
            {"prompt_tokens": 10, "completion_tokens": 10}
        )
        
        mock_prompt_service = MagicMock()
        mock_prompt_service.render_prompt.return_value = "Rendered Prompt"
        mock_prompt_service.get_system_message.return_value = "System Message"
        
        with patch.object(service, '_get_llm_service', return_value=mock_llm), \
             patch('app.services.llm_service.prompt_service', mock_prompt_service), \
             patch('app.services.llm_utils.extract_json_from_response', return_value={"diagnoses": ["Asthma"], "medications": []}):
            
            result = await service.extract_clinical_information("Patient has asthma")
            assert result["diagnoses"] == ["Asthma"]
            assert mock_llm.chat_completion.called

    def test_add_source_information_simple(self, service):
        """Test source information mapping stub"""
        data = {"diagnoses": ["Test"]}
        mapping = {1: "text"}
        result = service._add_source_information(data, mapping, "full text")
        assert result == data  # Currently returns data as-is in implementation
