import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from sqlalchemy.orm import Session
from app.services.main_agent import MainAgent, FollowUpResponse, ConversationMessage
from app.services.rag_retriever import RAGContext, RetrievedChunk
from app.models.document_chunk import SectionType
from datetime import datetime

@pytest.fixture
def main_agent():
    return MainAgent()

@pytest.fixture
def mock_db():
    return MagicMock(spec=Session)

@pytest.fixture
def mock_rag_context():
    chunk = RetrievedChunk(
        chunk_id="chunk-1",
        vector_id="vec-1",
        case_id="case-1",
        file_id="file-1",
        page_number=1,
        section_type=SectionType.CLINICAL,
        chunk_text="Patient has hypertension.",
        score=0.9,
        char_start=0,
        char_end=25,
        token_count=5
    )
    return RAGContext(
        chunks=[chunk],
        total_tokens=5,
        formatted_context="--- Section: CLINICAL | Page 1 ---\nPatient has hypertension.",
        source_references=[{
            "chunk_id": "chunk-1",
            "vector_id": "vec-1",
            "file_id": "file-1",
            "page_number": 1,
            "section_type": "clinical",
            "score": 0.9
        }]
    )

@pytest.mark.asyncio
async def test_answer_follow_up_question(main_agent, mock_db, mock_rag_context):
    with patch.object(main_agent, "_get_conversation_history", return_value=[]), \
         patch.object(main_agent, "_get_dashboard_context", return_value="Dashboard context"), \
         patch.object(main_agent, "_retrieve_relevant_context", return_value=mock_rag_context), \
         patch("app.services.main_agent.prompt_service.render_prompt", return_value="Mock prompt"), \
         patch.object(main_agent, "_get_llm_response", new_callable=AsyncMock) as mock_llm, \
         patch.object(main_agent, "_add_to_history") as mock_add_history:
        
        mock_llm.return_value = ("The patient has hypertension.", 0.9)
        
        response = await main_agent.answer_follow_up_question(
            mock_db, "case-1", "Does the patient have hypertension?", "user-1"
        )
        
        assert isinstance(response, FollowUpResponse)
        assert response.answer == "The patient has hypertension."
        assert len(response.sources) == 1
        assert response.confidence == 0.9
        assert mock_add_history.call_count == 2 # Once for user, once for assistant

def test_estimate_confidence(main_agent):
    assert main_agent._estimate_confidence("The patient has hypertension.") == 0.8
    assert main_agent._estimate_confidence("I'm not sure if the patient has hypertension.") < 0.8
    assert main_agent._estimate_confidence("According to the record on page 1, the patient has hypertension.") > 0.8

def test_extract_suggested_actions(main_agent):
    actions = main_agent._extract_suggested_actions("See page 5 for details.", "What are the labs?")
    assert "View source document" in actions
    assert "Review lab results" in actions

def test_clear_conversation_history(main_agent, mock_db):
    with patch("app.repositories.conversation_repository.conversation_repository.clear_conversation") as mock_clear:
        main_agent.clear_conversation_history(mock_db, "case-1", "user-1")
        mock_clear.assert_called_once_with(mock_db, "case-1", "user-1")
