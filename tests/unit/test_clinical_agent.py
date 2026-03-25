import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from sqlalchemy.orm import Session
from app.services.clinical_agent import ClinicalAgent, ExtractionResult
from app.services.rag_retriever import RAGContext, RetrievedChunk
from app.models.document_chunk import SectionType

@pytest.fixture
def clinical_agent():
    return ClinicalAgent()

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
        chunk_text="Patient has hypertension and is taking Lisinopril 10mg.",
        score=0.9,
        char_start=0,
        char_end=50,
        token_count=10
    )
    return RAGContext(
        chunks=[chunk],
        total_tokens=10,
        formatted_context="--- Section: CLINICAL | Page 1 ---\nPatient has hypertension and is taking Lisinopril 10mg.",
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
async def test_extract_medications(clinical_agent, mock_db, mock_rag_context):
    with patch("app.services.clinical_agent.rag_retriever.build_section_context", return_value=mock_rag_context), \
         patch("app.services.clinical_agent.prompt_service.render_prompt", return_value="Mock prompt"), \
         patch.object(clinical_agent, "_call_llm", new_callable=AsyncMock) as mock_llm:
        
        mock_llm.return_value = {"medications": [{"name": "Lisinopril", "dosage": "10mg"}]}
        
        result = await clinical_agent.extract_medications(mock_db, "case-1", "user-1")
        
        assert isinstance(result, ExtractionResult)
        assert len(result.data["medications"]) == 1
        assert result.data["medications"][0]["name"] == "Lisinopril"
        assert len(result.sources) == 1
        assert result.sources[0]["chunk_id"] == "chunk-1"

@pytest.mark.asyncio
async def test_extract_all_parallel(clinical_agent, mock_db, mock_rag_context):
    with patch("app.services.clinical_agent.rag_retriever.build_section_context", return_value=mock_rag_context), \
         patch("app.services.clinical_agent.prompt_service.render_prompt", return_value="Mock prompt"), \
         patch("app.repositories.chunk_repository.chunk_repository.count_by_case", return_value=1), \
         patch.object(clinical_agent, "_call_llm", new_callable=AsyncMock) as mock_llm:
        
        # Mocking 6 LLM calls (meds, labs, diag, history, social, therapy)
        mock_llm.side_effect = [
            {"medications": [{"name": "Meds"}], "allergies": []}, # Meds/Allergies
            {"labs": [], "imaging": [], "vitals": []},           # Labs/Imaging/Vitals
            {"diagnoses": [{"name": "Dx"}], "procedures": []},   # Diagnoses/Procedures
            {"chief_complaint": "Pain", "history": []},          # History
            {"social_factors": []},                              # Social
            {"therapy_notes": []}                                # Therapy
        ]
        
        result = await clinical_agent.extract_all(mock_db, "case-1", "user-1")
        
        assert isinstance(result, ExtractionResult)
        assert len(result.data["medications"]) == 1
        assert result.data["diagnoses"][0]["name"] == "Dx"
        assert result.data["chief_complaint"] == "Pain"
        assert len(result.chunks_used) > 0

@pytest.mark.asyncio
async def test_extract_generic_no_chunks(clinical_agent, mock_db):
    empty_context = RAGContext(chunks=[], total_tokens=0, formatted_context="", source_references=[])
    
    with patch("app.services.clinical_agent.rag_retriever.build_section_context", return_value=empty_context):
        result = await clinical_agent.extract_medications(mock_db, "case-1", "user-1")
        
        assert result.data == {"medications": []}
        assert result.sources == []
        assert result.chunks_used == []

def test_build_sources(clinical_agent, mock_rag_context):
    sources = clinical_agent._build_sources(mock_rag_context, "medication")
    
    assert len(sources) == 1
    assert sources[0]["type"] == "medication"
    assert sources[0]["chunk_id"] == "chunk-1"
    assert sources[0]["file_id"] == "file-1"


@pytest.mark.asyncio
async def test_call_llm_retries_when_parsed_json_is_list_then_succeeds(clinical_agent):
    mock_llm = MagicMock()
    mock_llm.is_available.return_value = True
    mock_llm.chat_completion = AsyncMock(
        side_effect=[
            ("[null, null]", {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12}),
            ('{"medications": [], "allergies": []}', {"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14}),
        ]
    )

    with patch.object(clinical_agent, "_get_llm_service", return_value=mock_llm), \
         patch("app.services.clinical_agent.prompt_service.get_system_message", return_value="system"), \
         patch("app.services.llm_utils.extract_json_from_response", side_effect=[[None, None], {"medications": [], "allergies": []}]):
        result = await clinical_agent._call_llm(
            prompt="prompt",
            prompt_id="meds_allergies_extraction",
        )

    assert result == {"medications": [], "allergies": []}
    assert mock_llm.chat_completion.await_count == 2


@pytest.mark.asyncio
async def test_call_llm_returns_empty_dict_after_repeated_non_dict_json(clinical_agent):
    mock_llm = MagicMock()
    mock_llm.is_available.return_value = True
    mock_llm.chat_completion = AsyncMock(
        side_effect=[
            ("[null]", {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}),
            ("[null]", {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}),
            ("[null]", {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}),
        ]
    )

    with patch.object(clinical_agent, "_get_llm_service", return_value=mock_llm), \
         patch("app.services.clinical_agent.prompt_service.get_system_message", return_value="system"), \
         patch("app.services.llm_utils.extract_json_from_response", return_value=[None]):
        result = await clinical_agent._call_llm(
            prompt="prompt",
            prompt_id="meds_allergies_extraction",
        )

    assert result == {}
    assert mock_llm.chat_completion.await_count == 3
