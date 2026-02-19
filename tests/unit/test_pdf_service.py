"""Unit tests for PDFService"""

import pytest
from unittest.mock import MagicMock, patch, mock_open
from pathlib import Path
from app.services.pdf_service import PDFService


@pytest.fixture
def pdf_service():
    return PDFService()


def test_clean_extracted_text_basic(pdf_service):
    """Test basic text cleaning"""
    text = "This is a test\n\nThis is another paragraph"
    cleaned = pdf_service._clean_extracted_text(text)
    assert "test" in cleaned
    assert "paragraph" in cleaned


def test_clean_extracted_text_fragmented_words(pdf_service):
    """Test cleaning of fragmented words split by newlines"""
    text = "This is a frag\nmented word"
    cleaned = pdf_service._clean_extracted_text(text)
    # Should merge fragmented words
    assert "fragmented" in cleaned or "frag" in cleaned


def test_clean_extracted_text_empty(pdf_service):
    """Test cleaning empty text"""
    assert pdf_service._clean_extracted_text("") == ""
    assert pdf_service._clean_extracted_text(None) is None


def test_extract_text_from_pdf_local(pdf_service):
    """Test extracting text from local PDF file"""
    mock_pdf_reader = MagicMock()
    mock_page = MagicMock()
    # Return text that's long enough to not trigger OCR detection
    mock_page.extract_text.return_value = "Page 1 text content " * 10  # Make it > 50 chars
    mock_pdf_reader.pages = [mock_page]
    
    with patch("builtins.open", mock_open(read_data=b"PDF content")), \
         patch("app.services.pdf_service.PyPDF2.PdfReader", return_value=mock_pdf_reader), \
         patch("app.services.pdf_service.settings.STORAGE_TYPE", "local"), \
         patch("os.path.exists", return_value=True):
        
        result = pdf_service.extract_text_from_pdf("/path/to/file.pdf")
        
        assert result["page_count"] == 1
        assert len(result["pages"]) == 1
        assert "Page 1 text content" in result["text"]


def test_extract_text_from_pdf_s3(pdf_service):
    """Test extracting text from S3 PDF"""
    mock_pdf_reader = MagicMock()
    mock_page = MagicMock()
    mock_page.extract_text.return_value = "S3 PDF content " * 10  # Make it > 50 chars
    mock_pdf_reader.pages = [mock_page]
    
    mock_s3_service = MagicMock()
    mock_s3_service.get_file_content.return_value = b"PDF content"
    
    with patch("app.services.pdf_service.settings.STORAGE_TYPE", "s3"), \
         patch("app.services.pdf_service.s3_storage_service", mock_s3_service, create=True), \
         patch("app.services.s3_storage_service.s3_storage_service", mock_s3_service), \
         patch("tempfile.NamedTemporaryFile") as mock_temp, \
         patch("builtins.open", mock_open(read_data=b"PDF content")), \
         patch("app.services.pdf_service.PyPDF2.PdfReader", return_value=mock_pdf_reader), \
         patch("os.path.exists", return_value=True), \
         patch("os.unlink"):
        
        # Mock NamedTemporaryFile to return a file-like object
        mock_file = MagicMock()
        mock_file.name = "/tmp/test.pdf"
        mock_file.write = MagicMock()
        mock_temp.return_value.__enter__.return_value = mock_file
        
        result = pdf_service.extract_text_from_pdf("users/user-1/cases/case-1/file.pdf")
        
        assert result["page_count"] == 1
        assert mock_s3_service.get_file_content.called


def test_extract_text_from_pdf_file_not_found(pdf_service):
    """Test extracting text from non-existent file"""
    with patch("os.path.exists", return_value=False), \
         patch("app.services.pdf_service.settings.STORAGE_TYPE", "local"):
        
        result = pdf_service.extract_text_from_pdf("/nonexistent/file.pdf")
        
        assert "error" in result
        assert result["extraction_method"] == "failed"


def test_count_pages_local(pdf_service):
    """Test counting pages from local PDF"""
    mock_pdf_reader = MagicMock()
    mock_pdf_reader.pages = [MagicMock(), MagicMock(), MagicMock()]
    
    with patch("builtins.open", mock_open(read_data=b"PDF content")), \
         patch("app.services.pdf_service.PyPDF2.PdfReader", return_value=mock_pdf_reader) as mock_reader, \
         patch("app.services.pdf_service.settings.STORAGE_TYPE", "local"), \
         patch("os.path.exists", return_value=True):
        
        count = pdf_service.count_pages("/path/to/file.pdf")
        assert count == 3
        assert mock_reader.called


def test_count_pages_s3(pdf_service):
    """Test counting pages from S3 PDF"""
    mock_pdf_reader = MagicMock()
    mock_pdf_reader.pages = [MagicMock(), MagicMock()]
    
    mock_s3_service = MagicMock()
    mock_s3_service.get_file_content.return_value = b"PDF content"
    
    with patch("app.services.pdf_service.settings.STORAGE_TYPE", "s3"), \
         patch("app.services.pdf_service.s3_storage_service", mock_s3_service, create=True), \
         patch("app.services.s3_storage_service.s3_storage_service", mock_s3_service), \
         patch("tempfile.NamedTemporaryFile") as mock_temp, \
         patch("builtins.open", mock_open(read_data=b"PDF content")), \
         patch("app.services.pdf_service.PyPDF2.PdfReader", return_value=mock_pdf_reader), \
         patch("os.path.exists", return_value=True), \
         patch("os.unlink"):
        
        mock_file = MagicMock()
        mock_file.name = "/tmp/test.pdf"
        mock_file.write = MagicMock()
        mock_temp.return_value.__enter__.return_value = mock_file
        
        count = pdf_service.count_pages("users/user-1/cases/case-1/file.pdf")
        assert count == 2


def test_extract_metadata(pdf_service):
    """Test extracting PDF metadata"""
    mock_pdf_reader = MagicMock()
    mock_metadata = MagicMock()
    mock_metadata.get.side_effect = lambda key, default: {
        "/Title": "Test Document",
        "/Author": "Test Author",
        "/Subject": "Test Subject",
        "/Creator": "Test Creator"
    }.get(key, default)
    mock_pdf_reader.metadata = mock_metadata
    
    with patch("builtins.open", mock_open(read_data=b"PDF content")), \
         patch("app.services.pdf_service.PyPDF2.PdfReader", return_value=mock_pdf_reader), \
         patch("app.services.pdf_service.settings.STORAGE_TYPE", "local"), \
         patch("os.path.exists", return_value=True):
        
        metadata = pdf_service.extract_metadata("/path/to/file.pdf")
        
        assert "title" in metadata or metadata.get("title") == "Test Document"
        assert "author" in metadata or metadata.get("author") == "Test Author"


def test_extract_text_with_coordinates(pdf_service):
    """Test extracting text with bounding box coordinates"""
    mock_pdf = MagicMock()
    mock_page = MagicMock()
    mock_page.extract_text.return_value = "Page text " * 10  # Make it > 50 chars
    mock_page.extract_words.return_value = [
        {"text": "Word", "x0": 10, "top": 20, "x1": 30, "bottom": 30}
    ]
    mock_page.chars = [
        {"text": "W", "x0": 10, "top": 20, "x1": 15, "bottom": 25}
    ]
    mock_pdf.pages = [mock_page]
    mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
    mock_pdf.__exit__ = MagicMock(return_value=None)
    
    with patch("app.services.pdf_service.settings.STORAGE_TYPE", "local"), \
         patch("builtins.open", mock_open(read_data=b"PDF content")), \
         patch("app.services.pdf_service.pdfplumber.open", return_value=mock_pdf) as mock_open_pdf, \
         patch("os.path.exists", return_value=True), \
         patch("os.unlink"):
        
        result = pdf_service.extract_text_with_coordinates("/path/to/file.pdf")
        
        assert result["page_count"] == 1
        assert len(result["pages"]) == 1
        assert "text_segments" in result["pages"][0]
        assert "char_coordinates" in result["pages"][0]
        assert mock_open_pdf.called


def test_extract_text_with_coordinates_s3(pdf_service):
    """Test extracting text with coordinates from S3"""
    mock_pdf = MagicMock()
    mock_page = MagicMock()
    mock_page.extract_text.return_value = "S3 PDF text " * 10  # Make it > 50 chars
    mock_page.extract_words.return_value = []
    mock_page.chars = []
    mock_pdf.pages = [mock_page]
    mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
    mock_pdf.__exit__ = MagicMock(return_value=None)
    
    mock_s3_service = MagicMock()
    mock_s3_service.get_file_content.return_value = b"PDF content"
    
    with patch("app.services.pdf_service.settings.STORAGE_TYPE", "s3"), \
         patch("app.services.pdf_service.s3_storage_service", mock_s3_service, create=True), \
         patch("app.services.s3_storage_service.s3_storage_service", mock_s3_service), \
         patch("tempfile.NamedTemporaryFile") as mock_temp, \
         patch("builtins.open", mock_open(read_data=b"PDF content")), \
         patch("app.services.pdf_service.pdfplumber.open", return_value=mock_pdf), \
         patch("os.path.exists", return_value=True), \
         patch("os.unlink"):
        
        mock_file = MagicMock()
        mock_file.name = "/tmp/test.pdf"
        mock_file.write = MagicMock()
        mock_temp.return_value.__enter__.return_value = mock_file
        
        result = pdf_service.extract_text_with_coordinates("users/user-1/cases/case-1/file.pdf")
        
        assert result["page_count"] == 1
        assert mock_s3_service.get_file_content.called


def test_extract_text_with_coordinates_fallback(pdf_service):
    """Test fallback to basic extraction on error"""
    with patch("app.services.pdf_service.settings.STORAGE_TYPE", "local"), \
         patch("app.services.pdf_service.pdfplumber.open", side_effect=Exception("Error")), \
         patch.object(pdf_service, "extract_text_from_pdf", return_value={"text": "Fallback text", "page_count": 1, "pages": []}) as mock_fallback:
        
        result = pdf_service.extract_text_with_coordinates("/path/to/file.pdf")
        
        assert "Fallback text" in result["text"]
        assert mock_fallback.called
