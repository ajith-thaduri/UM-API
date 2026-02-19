"""
Integration tests for extraction validation functionality
"""

import pytest
from app.services.clinical_agent import clinical_agent
from app.services.rag_retriever import RetrievedChunk
from app.models.document_chunk import SectionType


class TestExtractionValidation:
    """Test suite for extraction validation against source chunks"""
    
    def test_validated_items_have_metadata(self):
        """Test that validated items have is_verified and confidence_score"""
        # Mock extracted items
        extracted_items = [
            {"name": "Metformin", "dosage": "500mg"},
            {"name": "Lisinopril", "dosage": "10mg"}
        ]
        
        # Mock chunks with matching text
        mock_chunks = [
            RetrievedChunk(
                chunk_id="chunk-1",
                vector_id="vec-1",
                case_id="case-1",
                file_id="file-1",
                page_number=1,
                section_type=SectionType.UNKNOWN,
                chunk_text="Patient is taking Metformin 500mg twice daily",
                score=0.9,
                char_start=0,
                char_end=100,
                token_count=20
            ),
            RetrievedChunk(
                chunk_id="chunk-2",
                vector_id="vec-2",
                case_id="case-1",
                file_id="file-1",
                page_number=2,
                section_type=SectionType.UNKNOWN,
                chunk_text="Lisinopril 10mg was prescribed for hypertension",
                score=0.85,
                char_start=100,
                char_end=200,
                token_count=20
            )
        ]
        
        # Validate
        validated = clinical_agent._validate_extraction_against_chunks(
            extracted_items, mock_chunks, item_name_key="name"
        )
        
        # Assert validation metadata is added
        assert len(validated) == 2
        for item in validated:
            assert "is_verified" in item
            assert "confidence_score" in item
            assert "matching_chunks" in item
        
        # Both should be verified
        assert validated[0]["is_verified"] == True
        assert validated[1]["is_verified"] == True
        
        # Confidence scores should be > 0
        assert validated[0]["confidence_score"] > 0.5
        assert validated[1]["confidence_score"] > 0.5
    
    def test_unverified_items_have_low_confidence(self):
        """Test that items not found in chunks have low confidence"""
        # Mock extracted items - one not in chunks
        extracted_items = [
            {"name": "Aspirin", "dosage": "81mg"},
            {"name": "FabricatedDrug", "dosage": "100mg"}
        ]
        
        # Mock chunks - only contains Aspirin
        mock_chunks = [
            RetrievedChunk(
                chunk_id="chunk-1",
                vector_id="vec-1",
                case_id="case-1",
                file_id="file-1",
                page_number=1,
                section_type=SectionType.UNKNOWN,
                chunk_text="Patient takes Aspirin 81mg daily",
                score=0.9,
                char_start=0,
                char_end=100,
                token_count=20
            )
        ]
        
        # Validate
        validated = clinical_agent._validate_extraction_against_chunks(
            extracted_items, mock_chunks, item_name_key="name"
        )
        
        # First item should be verified
        assert validated[0]["is_verified"] == True
        assert validated[0]["confidence_score"] > 0.5
        
        # Second item should NOT be verified
        assert validated[1]["is_verified"] == False
        assert validated[1]["confidence_score"] == 0.0
        assert len(validated[1]["matching_chunks"]) == 0
    
    def test_validation_doesnt_modify_original_data(self):
        """Test that validation only adds metadata, doesn't change original data"""
        # Mock extracted items
        extracted_items = [
            {"name": "Metformin", "dosage": "500mg", "frequency": "BID"}
        ]
        
        # Mock chunks
        mock_chunks = [
            RetrievedChunk(
                chunk_id="chunk-1",
                vector_id="vec-1",
                case_id="case-1",
                file_id="file-1",
                page_number=1,
                section_type=SectionType.UNKNOWN,
                chunk_text="Metformin 500mg BID",
                score=0.9,
                char_start=0,
                char_end=100,
                token_count=20
            )
        ]
        
        # Validate
        validated = clinical_agent._validate_extraction_against_chunks(
            extracted_items, mock_chunks, item_name_key="name"
        )
        
        # Original data should be preserved
        assert validated[0]["name"] == "Metformin"
        assert validated[0]["dosage"] == "500mg"
        assert validated[0]["frequency"] == "BID"
        
        # New metadata should be added
        assert "is_verified" in validated[0]
        assert "confidence_score" in validated[0]
    
    def test_validation_with_different_name_keys(self):
        """Test validation works with different item_name_key values"""
        # Test with "test_name" for labs
        lab_items = [
            {"test_name": "Glucose", "value": "120", "unit": "mg/dL"}
        ]
        
        mock_chunks = [
            RetrievedChunk(
                chunk_id="chunk-1",
                vector_id="vec-1",
                case_id="case-1",
                file_id="file-1",
                page_number=1,
                section_type=SectionType.UNKNOWN,
                chunk_text="Glucose level was 120 mg/dL",
                score=0.9,
                char_start=0,
                char_end=100,
                token_count=20
            )
        ]
        
        validated = clinical_agent._validate_extraction_against_chunks(
            lab_items, mock_chunks, item_name_key="test_name"
        )
        
        assert validated[0]["is_verified"] == True
        assert validated[0]["confidence_score"] > 0.5
    
    def test_empty_items_validation(self):
        """Test validation handles empty items list gracefully"""
        validated = clinical_agent._validate_extraction_against_chunks(
            [], [], item_name_key="name"
        )
        
        assert validated == []
    
    def test_confidence_score_calculation(self):
        """Test confidence score is calculated correctly"""
        extracted_items = [
            {"name": "Warfarin", "dosage": "5mg"}
        ]
        
        # Mock chunk with high score and multiple mentions
        mock_chunks = [
            RetrievedChunk(
                chunk_id="chunk-1",
                vector_id="vec-1",
                case_id="case-1",
                file_id="file-1",
                page_number=1,
                section_type=SectionType.UNKNOWN,
                chunk_text="Warfarin 5mg daily. Patient on Warfarin for AFib. Warfarin levels monitored.",
                score=0.95,
                char_start=0,
                char_end=200,
                token_count=30
            )
        ]
        
        validated = clinical_agent._validate_extraction_against_chunks(
            extracted_items, mock_chunks, item_name_key="name"
        )
        
        # Should have high confidence due to high chunk score and multiple mentions
        assert validated[0]["confidence_score"] > 0.7
