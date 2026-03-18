import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from app.services.pdf_analyzer_service import PDFAnalyzerService, PatientInfo, FileAnalysis, AnalysisResult

class TestPDFAnalyzerService:
    @pytest.fixture
    def service(self):
        return PDFAnalyzerService()

    def test_patient_info_is_complete(self):
        """Test is_complete method of PatientInfo"""
        info = PatientInfo(name="John Doe")
        assert info.is_complete() is True
        
        info = PatientInfo(name=None)
        assert info.is_complete() is False

    def test_patient_info_get_missing_fields(self):
        """Test get_missing_fields method of PatientInfo"""
        info = PatientInfo(name="John Doe", dob=None, mrn=None)
        missing = info.get_missing_fields()
        assert "dob" in missing
        assert "mrn" in missing
        assert "patient_name" not in missing

    def test_clean_extracted_value_name(self, service):
        """Test name cleaning including LAST, FIRST format"""
        # Test title case
        assert service._clean_extracted_value("name", "john doe") == "John Doe"
        # Test LAST, FIRST format
        assert service._clean_extracted_value("name", "DOE, JOHN") == "John Doe"

    def test_clean_extracted_value_gender(self, service):
        """Test gender normalization"""
        assert service._clean_extracted_value("gender", "m") == "Male"
        assert service._clean_extracted_value("gender", "FEMALE") == "Female"

    def test_normalize_date(self, service):
        """Test date normalization to MM/DD/YYYY"""
        assert service._normalize_date("1/2/2023") == "01/02/2023"
        assert service._normalize_date("12-31-99") == "12/31/1999"
        assert service._normalize_date("05/20/40") == "05/20/2040"

    def test_is_valid_name(self, service):
        """Test name validation logic"""
        assert service._is_valid_name("John Doe") is True
        assert service._is_valid_name("Dr. Jane Smith") is True  # Should pass now
        assert service._is_valid_name("John") is False  # Too short/one word
        assert service._is_valid_name("Medical Record") is False  # Invalid term

    def test_extract_patient_info_regex(self, service):
        """Test regex extraction from text"""
        text = "Patient Name: Jane Smith\nDOB: 05/15/1985\nMRN: 12345678\nSex: Female"
        info = service._extract_patient_info_regex(text)
        assert info.name == "Jane Smith"
        assert info.dob == "05/15/1985"
        assert info.mrn == "12345678"
        assert info.gender == "Female"

    def test_detect_document_type(self, service):
        """Test document type detection from indicators"""
        # Lab report
        text = "Laboratory results show normal CBC and CMP values."
        doc_type, confidence = service._detect_document_type(text)
        assert doc_type == "lab_report"
        
        # Imaging
        text = "Radiology report for CT Scan of the chest."
        doc_type, confidence = service._detect_document_type(text)
        assert doc_type == "imaging"

    @pytest.mark.asyncio
    async def test_analyze_for_upload_error_handling(self, service):
        """Test analyze_for_upload handles file errors gracefully"""
        with patch.object(service, '_analyze_single_file', side_effect=Exception("File error")):
            result = await service.analyze_for_upload(["nonexistent.pdf"])
            assert len(result.files) == 1
            assert result.files[0].detected_type == "unknown"
            assert result.files[0].extraction_preview == "[Error extracting text]"

    def test_merge_patient_info(self, service):
        """Test merging regex and LLM results"""
        regex_info = PatientInfo(name="John Doe", dob="01/01/1980")
        llm_info = PatientInfo(name="John Doe", mrn="99999", diagnosis="Asthma")
        
        merged = service._merge_patient_info(regex_info, llm_info)
        assert merged.name == "John Doe"
        assert merged.dob == "01/01/1980"
        assert merged.mrn == "99999"
        assert merged.diagnosis == "Asthma"
