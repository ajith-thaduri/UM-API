import pytest
from app.services.chunking_service import ChunkingService, ChunkData
from app.models.document_chunk import SectionType

class TestChunkingService:
    @pytest.fixture
    def service(self):
        return ChunkingService()

    def test_count_tokens(self, service):
        """Test token counting"""
        text = "Hello world"
        # "Hello world" is typically 2 tokens in tiktoken gpt-4
        count = service.count_tokens(text)
        assert count > 0

    def test_split_into_sentences(self, service):
        """Test medical-aware sentence splitting"""
        text = "Patient has B.P. of 120/80. Dr. Smith reviewed the case. Weight is 150.5 lbs."
        sentences = service._split_into_sentences(text)
        
        assert len(sentences) >= 3
        assert "B.P." in sentences[0]
        assert "Dr. Smith" in sentences[1]
        assert "150.5" in sentences[2]

    def test_chunk_page_text_simple(self, service):
        """Test chunking simple text that fits in one chunk"""
        text = "This is a simple document with only one sentence."
        chunks = service.chunk_page_text(
            text=text,
            page_number=1,
            file_id="file-1",
            case_id="case-1"
        )
        
        assert len(chunks) == 1
        assert chunks[0].chunk_text == text
        assert chunks[0].page_number == 1
        assert chunks[0].section_type == SectionType.UNKNOWN

    def test_get_overlap_sentences(self, service):
        """Test overlap sentence selection"""
        sentences = ["Sentence one.", "Sentence two.", "Sentence three."]
        # With small overlap, should only get last sentence
        overlap = service._get_overlap_sentences(sentences, 5)
        assert len(overlap) >= 1
        assert overlap[-1] == "Sentence three."

    def test_chunk_document(self, service):
        """Test chunking multiple pages"""
        mapping = {
            1: "Page one text.",
            2: "Page two text."
        }
        chunks = service.chunk_document(mapping, "file-1", "case-1")
        
        assert len(chunks) >= 2
        assert any(c.page_number == 1 for c in chunks)
        assert any(c.page_number == 2 for c in chunks)

    def test_chunk_page_with_bbox(self, service):
        """Test chunking with bounding box preservation"""
        text = "Hello world"
        segments = [
            {"text": "Hello world", "bbox": {"x0": 10, "y0": 20, "x1": 100, "y1": 50}}
        ]
        chunks = service.chunk_page_with_bbox(
            text=text,
            text_segments=segments,
            page_number=1,
            file_id="file-1",
            case_id="case-1"
        )
        
        assert len(chunks) == 1
        assert chunks[0].bbox == {"x0": 10, "y0": 20, "x1": 100, "y1": 50}
